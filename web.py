"""Unified browser UI for Ami — Amazon support agent.

Production-grade: authentication, per-user isolation, rate limiting, audit logging.
Stage 3: combines Stage 1's auth + Stage 2's policy layer + both planners.

    python3 web.py        then open http://localhost:9001

One session per browser (cookie), one UI, one unified codebase.
"""

import json
import os
import uuid
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta
from urllib.parse import urlparse

from ami import agent_profile as profile
from ami import dashboard
from ami import observe
from ami import planner
from ami import policy
from ami import route
from ami.config import config
from ami.llm import MODEL
from ami.memory import ConversationMemory, LongTermMemory, WorkingMemory
from ami import ROOT
from ami.auth import authenticate_request, AuthError
from ami.rate_limit import check_and_consume
from ami.audit import log_action
from ami.scope import derive_scope, ScopeError
from ami.query_classifier import classify_query, requires_authentication, get_login_prompt
from ami.users import verify_credentials
from ami.auth import generate_token

PORT = config.PORT
# The same system prompt the evals measure: profile + the ReAct planning
# rules. The web conversation used to start from the profile alone, so what
# shipped was not what was scored.
SYSTEM = profile.system_prompt() + planner.PLANNING_RULES

# Session persistence with batching
LONGTERM = LongTermMemory()
SESSIONS = {}
SESSIONS_FILE = ROOT / "state" / "sessions.json"
FEEDBACK_FILE = ROOT / "state" / "feedback.jsonl"

SECRET_KEY = config.SECRET_KEY
SESSION_TIMEOUT_HOURS = config.SESSION_TIMEOUT_HOURS

# Session write batching: dirty flag + timer-based flush
_session_dirty = False
_session_flush_timer = None
_session_flush_lock = threading.Lock()


def load_sessions():
    try:
        raw = json.loads(SESSIONS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return

    now = datetime.utcnow()
    cutoff = now - timedelta(hours=SESSION_TIMEOUT_HOURS)
    expired_count = 0

    for sid, d in raw.items():
        # Check if session has expired
        created_at = d.get("created_at")
        if created_at:
            try:
                session_time = datetime.fromisoformat(created_at)
                if session_time < cutoff:
                    expired_count += 1
                    continue  # Skip expired session
            except (ValueError, TypeError):
                pass  # Skip if date parsing fails

        work = WorkingMemory.from_dict(d["work"])
        # CRITICAL SECURITY: Clear scope when loading from disk
        # Authentication must come from JWT token ONLY, never from saved session
        work.scope = None
        work.authenticated = False

        # CRITICAL: Unauthenticated sessions should NOT restore conversation history
        # Only authenticated users (with valid JWT token) can resume conversations
        # This prevents data leakage when browser is shared or localStorage is cleared
        original_user_id = d.get("user_id")
        if original_user_id:
            # Authenticated session: restore full conversation
            convo = ConversationMemory.from_dict(SYSTEM, d["convo"])
        else:
            # Unauthenticated session: start fresh (no conversation history)
            convo = ConversationMemory(SYSTEM)
        SESSIONS[sid] = {
            "convo": convo,
            "work": work,
            "user_id": None,
            "created_at": created_at or datetime.utcnow().isoformat(),
        }
    print(f"restored {len(SESSIONS)} session(s) from {SESSIONS_FILE.name} "
          f"({expired_count} expired sessions removed)", flush=True)


load_sessions()


def _flush_sessions_async():
    """Background flush: writes sessions to disk asynchronously."""
    global _session_dirty, _session_flush_timer
    with _session_flush_lock:
        if _session_dirty:
            _flush_sessions_sync()
            _session_dirty = False
        _session_flush_timer = None


def _flush_sessions_sync():
    """Synchronous flush: serialize and write all sessions to disk."""
    try:
        SESSIONS_FILE.parent.mkdir(exist_ok=True)
        raw = {}
        for sid, session in SESSIONS.items():
            raw[sid] = {
                "convo": session["convo"].to_dict(),
                "work": session["work"].to_dict(),
                "created_at": session.get("created_at", datetime.utcnow().isoformat()),
            }
        SESSIONS_FILE.write_text(json.dumps(raw))
    except OSError:
        pass


def mark_sessions_dirty():
    """Mark sessions as dirty and schedule async flush."""
    global _session_dirty, _session_flush_timer
    with _session_flush_lock:
        _session_dirty = True
        if not _session_flush_timer:
            # Schedule flush after delay (batches multiple requests)
            _session_flush_timer = threading.Timer(
                config.SESSION_SAVE_INTERVAL_SECONDS,
                _flush_sessions_async
            )
            _session_flush_timer.daemon = True
            _session_flush_timer.start()


def save_sessions():
    """Public API: mark sessions dirty for async flush."""
    mark_sessions_dirty()


def new_session(user_id=None):
    return {
        "convo": ConversationMemory(SYSTEM),
        "work": WorkingMemory(scope=user_id),
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
    }


def save_feedback(golden_row_id, original_response, corrected_response, reason):
    try:
        FEEDBACK_FILE.parent.mkdir(exist_ok=True)
        feedback_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "golden_row_id": golden_row_id,
            "original_response": original_response,
            "corrected_response": corrected_response,
            "reason": reason
        }
        with open(FEEDBACK_FILE, "a") as f:
            f.write(json.dumps(feedback_entry) + "\n")
    except OSError:
        pass


def state(session, user_id=None):
    """Everything the page needs to redraw its panels."""
    work = session["work"]
    convo = session["convo"]

    # Extract conversation history for UI redraw
    history = []
    for msg in convo.history:
        if msg.get("role") == "user":
            history.append({"role": "user", "content": msg.get("content", "")})
        elif msg.get("role") == "assistant":
            # Extract just the text message, not tool_calls
            if "content" in msg:
                history.append({"role": "assistant", "content": msg.get("content", "")})

    # Personalized greeting based on auth state
    # Always use personalized greeting if authenticated (regardless of history)
    if user_id:
        username = user_id.split("@")[0] if "@" in user_id else user_id
        greeting = f"Welcome back {username}! How can I help you today?"
    else:
        # Default greeting for unauthenticated users
        greeting = profile.GREETING

    return {
        "working": work.brief() or "(empty — nothing established yet)",
        "messages": len(convo.history),
        "orders": len(work.orders),
        "actions": work.actions,
        "escalation": work.escalation,
        "longterm": LONGTERM.recall(work.customer_email, getattr(work, "session_id", None)) if user_id else None,
        "history": history,
        "greeting": greeting,
    }


PAGE = (ROOT / "ui" / "chat.html").read_text()
PAGE = PAGE.replace("__MODEL__", MODEL).replace("__GREETING__", json.dumps(profile.GREETING))


class Handler(BaseHTTPRequestHandler):

    def _authenticate(self):
        """Extract and validate user from HTTP-only auth cookie."""
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookie["auth_token"].value if "auth_token" in cookie else None

        if not token:
            raise AuthError("Missing auth token cookie")

        try:
            # Validate the token directly (construct Bearer header for validation)
            payload = authenticate_request(f"Bearer {token}", secret_key=SECRET_KEY)
            user_id = payload.get("user_id")
            scope = derive_scope(payload)
            return user_id, scope
        except (AuthError, ScopeError) as e:
            raise AuthError(f"Authentication failed: {e}")

    def _session(self, user_id=None):
        """Find or mint this browser's session."""
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        sid = cookie["sid"].value if "sid" in cookie else None
        self.stale = bool(sid) and sid not in SESSIONS

        # Check if session has expired
        if sid in SESSIONS:
            created_at = SESSIONS[sid].get("created_at")
            if created_at:
                try:
                    session_time = datetime.fromisoformat(created_at)
                    if datetime.utcnow() - session_time > timedelta(hours=SESSION_TIMEOUT_HOURS):
                        self.stale = True
                        del SESSIONS[sid]
                        sid = None
                except (ValueError, TypeError):
                    pass

        if sid not in SESSIONS:
            sid = uuid.uuid4().hex
            SESSIONS[sid] = new_session(user_id=user_id)
            self._set_cookie = sid

        # If authenticating with a token, always adopt that authenticated user
        # This prevents old session state from bleeding into new authenticated requests
        if user_id:
            SESSIONS[sid]["user_id"] = user_id
            SESSIONS[sid]["work"].scope = user_id
            SESSIONS[sid]["work"].authenticated = True
        elif not user_id and SESSIONS[sid].get("user_id"):
            # Unauthenticated request but session has old user_id from disk
            # Clear it to prevent data leakage
            SESSIONS[sid]["user_id"] = None
            SESSIONS[sid]["work"].scope = None
            SESSIONS[sid]["work"].authenticated = False

        return sid, SESSIONS[sid]

    def _send(self, body, content_type="application/json"):
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        if getattr(self, "_set_cookie", None):
            self.send_header("Set-Cookie", f"sid={self._set_cookie}; Path=/; SameSite=Lax")
            self._set_cookie = None
        if getattr(self, "_set_auth_cookie", None):
            # HTTP-only, Secure, SameSite=Strict: prevents XSS token theft
            cookie_value = self._set_auth_cookie
            self.send_header("Set-Cookie",
                           f"auth_token={cookie_value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=900")
            self._set_auth_cookie = None
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, location):
        """Send a 302 so the browser follows along to a page it can use."""
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        # Route on the path alone; a query string (e.g. /login?next=/logs) must
        # not change which handler runs.
        path = urlparse(self.path).path
        try:
            if path in ("/login", "/login.html"):
                login_page = (ROOT / "ui" / "login.html").read_text()
                self._send(login_page, "text/html")
                return

            if path in ("/", "/index.html"):
                self._session()
                self._send(PAGE, "text/html")
                return

            # /state: optional auth
            if path == "/state":
                user_id = None
                try:
                    user_id, _ = self._authenticate()
                except AuthError:
                    pass
                _, session = self._session(user_id=user_id)
                self._send(json.dumps({**state(session, user_id), "stale": self.stale}))
                return

            # /logs: requires auth. The page itself redirects an unauthenticated
            # browser to the login form (and back here after) rather than showing
            # a raw 401 you can't act on. The data endpoints below stay strict
            # 401s — they're fetched by JS, which wants a status code, not HTML.
            if path == "/logs":
                try:
                    self._authenticate()
                except AuthError:
                    self._redirect("/login?next=/logs")
                    return
                self._send(dashboard.PAGE, "text/html")
                return

            user_id, _ = self._authenticate()
            if path == "/logs.json":
                self._send(json.dumps({"stats": observe.stats(),
                                       "events": observe.recent(120),
                                       "alerts": observe.recent(20, kind="alert")}))
            elif path == "/trace.jsonl":
                try:
                    self._send(observe.LOGFILE.read_text(), "text/plain")
                except OSError:
                    self._send("", "text/plain")
            else:
                self.send_error(404)

        except AuthError as e:
            self.send_error(401, str(e))
        except Exception as e:
            self.send_error(500, str(e))

    def do_POST(self):
        try:
            # /login: no auth required
            if self.path == "/login":
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length) or "{}")
                email = data.get("email", "").strip()
                password = data.get("password", "")

                if not email or not password:
                    self.send_error(400, "Email and password required")
                    return

                if not verify_credentials(email, password):
                    log_action(None, "login", status="denied", http_status=401,
                              query_type="PRIVATE", details={"ip": self.client_address[0]})
                    self.send_error(401, "Invalid email or password")
                    return

                token = generate_token(email, secret_key=SECRET_KEY)
                log_action(email, "login", status="success", http_status=200,
                          query_type="PRIVATE", details={"ip": self.client_address[0]})
                # Set auth token as HTTP-only cookie (not in response body)
                self._set_auth_cookie = token
                self._send(json.dumps({"ok": True, "email": email}))
                return

            # All other POST endpoints require auth
            user_id = None
            try:
                user_id, _ = self._authenticate()
            except AuthError:
                # For /chat, auth is optional (query_type determines if it's needed)
                if self.path != "/chat":
                    self.send_error(401, "Authentication required")
                    return

            # Rate limit (only authenticated users)
            if user_id and not check_and_consume(user_id):
                log_action(user_id, "chat", status="rate_limited", http_status=429,
                          query_type="PRIVATE", details={"ip": self.client_address[0]})
                self.send_error(429, "Rate limit exceeded: 60 requests per minute")
                return

            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or "{}")
            sid, session = self._session(user_id=user_id)

            try:
                if self.path == "/reset":
                    # Reset clears EVERYTHING: conversation, working memory, AND authentication
                    # User is logged out; new_session with user_id=None starts fresh
                    SESSIONS[sid] = new_session(user_id=None)
                    save_sessions()
                    log_action(user_id, "reset", status="success", http_status=200,
                              query_type="PRIVATE" if user_id else "PUBLIC",
                              details={"ip": self.client_address[0]})
                    # Return state as unauthenticated (user_id=None) so client knows they're logged out
                    self._send(json.dumps({"ok": True, **state(SESSIONS[sid], user_id=None)}))
                    return

                if self.path == "/feedback":
                    golden_row_id = data.get("golden_row_id") or None
                    original_response = data.get("original_response", "").strip()
                    corrected_response = data.get("corrected_response", "").strip()
                    reason = data.get("reason", "").strip()

                    if original_response and corrected_response:
                        save_feedback(golden_row_id, original_response, corrected_response, reason)
                        log_action(user_id, "feedback", status="success", http_status=200,
                                  query_type="PRIVATE" if user_id else "PUBLIC",
                                  details={"ip": self.client_address[0]})
                        self._send(json.dumps({"ok": True, "message": "Feedback saved"}))
                    else:
                        log_action(user_id, "feedback", status="denied", http_status=400,
                                  query_type="PRIVATE" if user_id else "PUBLIC",
                                  details={"ip": self.client_address[0]})
                        self._send(json.dumps({"ok": False, "message": "Missing required fields"}))
                    return

                if self.path != "/chat":
                    self.send_error(404)
                    return

                text = (data.get("message") or "").strip()
                if not text:
                    query_type = "PUBLIC"
                    log_action(user_id, "chat", status="success", http_status=200,
                              query_type=query_type, details={"ip": self.client_address[0]})
                    self._send(json.dumps({"reply": "", "steps": [], **state(session, user_id)}))
                    return

                # Classify query
                query_type = classify_query(text)

                # Check auth requirement
                if requires_authentication(query_type) and not user_id:
                    log_action(None, "chat", status="login_required", http_status=403,
                              query_type=query_type, details={"ip": self.client_address[0], "message_preview": text[:100]})
                    self._send(json.dumps({
                        "reply": get_login_prompt(),
                        "requires_login": True,
                        "steps": [],
                        **state(session, user_id)
                    }))
                    return

                # Session pollution check
                if query_type == "PRIVATE" and not user_id:
                    log_action(None, "chat", status="security_violation", http_status=403,
                              query_type=query_type, details={"ip": self.client_address[0], "violation": "session_pollution"})
                    self._send(json.dumps({
                        "reply": get_login_prompt(),
                        "requires_login": True,
                        "steps": [],
                        **state(session, user_id)
                    }))
                    return

                convo, work = session["convo"], session["work"]
                before = len(work.actions)
                work.session_id = sid
                work.turn += 1

                observe.context(session=sid, user_id=user_id)
                turn_id = observe.new_turn()

                # Policy: input check — BEFORE the text enters memory, so a
                # pasted card number is scrubbed before the model ever sees it.
                try:
                    text, note = policy.check_input(text)
                except Exception as e:
                    reply = str(e)
                    LONGTERM.remember(work, session_id=sid)
                    self._send(json.dumps({"reply": reply, "steps": [], **state(session, user_id)}))
                    return

                convo.add_user(text)

                steps = []
                with observe.timer() as t:
                    try:
                        # Long-term memory and the policy note ride along
                        # with working memory on every step (planner.react
                        # reads `longterm` and `extra`). They used to be built
                        # here into a string that was never sent.
                        ltm = LONGTERM.recall(work.customer_email, sid)

                        # S6: pick the model tier for this turn from the
                        # query's difficulty (cheap for simple PUBLIC, strong
                        # for PRIVATE/account work). No-op unless MODEL_CHEAP
                        # is configured.
                        turn_model = route.pick_model(text, query_type)
                        reply = planner.react(convo, work, trace=False,
                                              steps=steps, model=turn_model,
                                              extra=note, longterm=LONGTERM)

                        # Policy: output check
                        reply = policy.check_output(reply, work, text,
                                                    context=ltm or "")

                        # Remember
                        LONGTERM.remember(work, session_id=sid)
                    except Exception as e:
                        # Degrade gracefully: the customer gets a calm, honest
                        # message and an offer to escalate — never a stack
                        # trace (bad UX, and a leak of internals). The real
                        # error goes to the trace for ops.
                        observe.log("degraded", reason="turn_exception",
                                    error=f"{type(e).__name__}: {e}")
                        reply = planner.DEGRADED_REPLY

                observe.log("turn", user=text, steps=len(steps), ms=t.ms,
                            actions=len(work.actions) - before,
                            cost=observe.turn_cost(turn_id))
                # S2: after each turn, check the live metrics against the
                # configured thresholds and raise an alert event on a breach.
                observe.check_alerts()
                save_sessions()

                log_action(user_id, "chat", status="success", http_status=200,
                          query_type=query_type,
                          details={"ip": self.client_address[0], "duration_ms": t.ms,
                                  "model_cost_usd": observe.turn_cost(turn_id)})
                self._send(json.dumps({"reply": reply, "steps": steps,
                                      "new_actions": work.actions[before:],
                                      **state(session, user_id)}))

            except Exception as e:
                log_action(user_id, self.path.lstrip('/'), status="error", http_status=500,
                          query_type="PRIVATE" if user_id else "PUBLIC",
                          details={"ip": self.client_address[0]})
                raise

        except Exception as e:
            self.send_error(500, str(e))

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Ami is running at http://localhost:{PORT}   (ctrl-c to stop)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
