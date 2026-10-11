"""Escalation tickets: a unique id per hand-off, a local record, and optional
delivery to a human queue (webhook, email or Jira).

Before this module the escalate tool returned the same string, ESC-4417, to
every customer, and nothing was stored or sent. Now:

  1. open_ticket() mints a unique ESC-<number> (numeric, so the policy
     layer's identifier check `ESC-\\d+` still recognises it) and appends an
     "opened" line to state/escalations.jsonl. This always happens, even with
     no backend configured, so there is a queue a human can read.
  2. deliver() hands the record to the configured backend, chosen by
     ESCALATION_BACKEND = none | webhook | email | jira. Default none.
     Delivery is best effort with a timeout: it never raises and never blocks
     the turn beyond ESCALATION_TIMEOUT_SECONDS. Success and failure are both
     logged as `escalation` events, so the /logs dashboard sees them.

Credentials live in .env only (see .env.example). The customer-facing ticket
number is always the local ESC id; an external reference (a Jira key, an
HTTP status, a mail id) is stored alongside it.
"""

import base64
import json
import smtplib
import threading
import time
import urllib.request
from email.message import EmailMessage

from ami import ROOT, observe
from ami.config import config

FILE = ROOT / "state" / "escalations.jsonl"
PREFIX = "ESC-"
FIRST_TICKET = 10001          # five digits from day one, no leading zeros to lose

_lock = threading.Lock()


# --------------------------------------------------------------------------
# The local record
# --------------------------------------------------------------------------

def _append(line):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    with FILE.open("a") as f:
        f.write(json.dumps(line) + "\n")


def _records():
    try:
        with FILE.open() as f:
            for raw in f:
                raw = raw.strip()
                if raw:
                    try:
                        yield json.loads(raw)
                    except ValueError:
                        continue
    except OSError:
        return


def _last_number():
    last = FIRST_TICKET - 1
    for r in _records():
        t = str(r.get("ticket", ""))
        if t.startswith(PREFIX) and t[len(PREFIX):].isdigit():
            last = max(last, int(t[len(PREFIX):]))
    return last


def open_ticket(summary, customer=None):
    """Mint a unique ticket and record it. Returns the record (a dict)."""
    with _lock:                              # mint + append are one step
        ticket = f"{PREFIX}{_last_number() + 1}"
        ev = observe.log("escalation", ticket=ticket, status="opened",
                         backend=(config.ESCALATION_BACKEND or "none"),
                         customer=customer, summary=(summary or "")[:300])
        record = {
            "ticket": ticket, "status": "opened", "ts": ev["ts"],
            "session": ev.get("session"), "turn": ev.get("turn"),
            "customer": customer, "summary": summary or "",
        }
        _append(record)
    return record


def tickets(limit=50):
    """Tickets newest first, each folded to its latest status and reference."""
    folded = {}
    for r in _records():
        t = r.get("ticket")
        if not t:
            continue
        cur = folded.setdefault(t, {"ticket": t})
        cur.update({k: v for k, v in r.items() if v is not None})
    return sorted(folded.values(), key=lambda r: r.get("ts", 0), reverse=True)[:limit]


# --------------------------------------------------------------------------
# Delivery backends
# --------------------------------------------------------------------------

def _timeout():
    return max(1, int(config.ESCALATION_TIMEOUT_SECONDS or 5))


def _text(record):
    return (f"Ticket {record['ticket']}\n"
            f"Customer: {record.get('customer') or 'not logged in'}\n"
            f"Session: {record.get('session')}  Turn: {record.get('turn')}\n\n"
            f"Summary from the agent:\n{record.get('summary') or '(none)'}\n")


def _webhook(record):
    url = config.ESCALATION_WEBHOOK_URL
    if not url:
        raise ValueError("ESCALATION_WEBHOOK_URL is not set")
    body = json.dumps({"text": _text(record), **record}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=_timeout()) as resp:
        return f"HTTP {resp.status}"


def _email(record):
    missing = [k for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ESCALATION_TO")
               if not getattr(config, k, None)]
    if missing:
        raise ValueError("email backend needs " + ", ".join(missing))
    msg = EmailMessage()
    msg["Subject"] = f"[Ami] {record['ticket']}: customer hand-off"
    msg["From"] = config.ESCALATION_FROM or config.SMTP_USER
    to = [config.ESCALATION_TO]
    if config.ESCALATION_EMAIL_CUSTOMER and record.get("customer"):
        to.append(record["customer"])
    msg["To"] = ", ".join(to)
    msg.set_content(_text(record))
    with smtplib.SMTP(config.SMTP_HOST, int(config.SMTP_PORT or 587), timeout=_timeout()) as s:
        s.starttls()
        s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        s.send_message(msg)
    return f"mail to {', '.join(to)}"


def _jira(record):
    missing = [k for k in ("JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT")
               if not getattr(config, k, None)]
    if missing:
        raise ValueError("jira backend needs " + ", ".join(missing))
    auth = base64.b64encode(f"{config.JIRA_EMAIL}:{config.JIRA_API_TOKEN}".encode()).decode()
    payload = {"fields": {
        "project": {"key": config.JIRA_PROJECT},
        "issuetype": {"name": config.JIRA_ISSUE_TYPE or "Task"},
        "summary": f"{record['ticket']}: {(record.get('summary') or 'customer hand-off')[:120]}",
        "description": {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": _text(record)}]}]},
    }}
    req = urllib.request.Request(
        config.JIRA_URL.rstrip("/") + "/rest/api/3/issue",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(req, timeout=_timeout()) as resp:
        return json.loads(resp.read().decode()).get("key") or f"HTTP {resp.status}"


_BACKENDS = {"webhook": _webhook, "email": _email, "jira": _jira}


def deliver(record):
    """Send the ticket to the configured backend. Never raises.

    Returns the external reference (Jira key, mail recipients, HTTP status)
    or None when no backend is configured or delivery failed. Either way the
    outcome is appended to the local record and logged.
    """
    backend = (config.ESCALATION_BACKEND or "none").strip().lower()
    if backend == "none":
        return None
    t0 = time.perf_counter()
    try:
        fn = _BACKENDS.get(backend)
        if fn is None:
            raise ValueError(f"unknown ESCALATION_BACKEND '{backend}'")
        ref = fn(record)
        status, extra = "delivered", {"ref": ref}
    except Exception as e:                   # delivery is best effort, by design
        ref = None
        status, extra = "delivery_failed", {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    ms = round((time.perf_counter() - t0) * 1000)
    observe.log("escalation", ticket=record["ticket"], status=status, backend=backend, ms=ms, **extra)
    with _lock:
        _append({"ticket": record["ticket"], "status": status, "backend": backend,
                 "ts": time.time(), **extra})
    return ref
