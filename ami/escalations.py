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
import re
import smtplib
import threading
import time
import urllib.request
from email.message import EmailMessage

from ami import STATE_DIR, observe
from ami.config import config

FILE = STATE_DIR / "escalations.jsonl"
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


_ORDER_ID = re.compile(r"\b\d{3}-\d{7}-\d{7}\b")


def open_ticket(summary, customer=None, context=None):
    """Mint a unique ticket, route it, and record it. Returns the record."""
    from ami import routing                  # local import keeps module load light
    context = context or {}
    orders = dict(context.get("orders") or {})
    route = routing.route(summary, orders)
    # Order ids the agent wrote in its summary but never looked up: shown, flagged
    mentioned = [o for o in dict.fromkeys(_ORDER_ID.findall(summary or "")) if o not in orders]
    with _lock:                              # mint + append are one step
        ticket = f"{PREFIX}{_last_number() + 1}"
        ev = observe.log("escalation", ticket=ticket, status="opened",
                         backend=(config.ESCALATION_BACKEND or "none"),
                         customer=customer, summary=(summary or "")[:300],
                         category=route["category"], department=route["department"])
        record = {
            "ticket": ticket, "status": "opened", "ts": ev["ts"],
            "session": ev.get("session"), "turn": ev.get("turn"),
            "customer": customer, "summary": summary or "",
            "orders": orders, "orders_mentioned_unverified": mentioned,
            "refused": context.get("refused") or [], "done": context.get("done") or [],
            "routing": {k: route[k] for k in ("category", "department", "contact",
                                               "priority", "sla", "next_steps")},
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
    r = record.get("routing") or {}
    lines = [f"Ticket {record['ticket']}  |  {r.get('category', 'general_complaint')}  |  priority {r.get('priority', 'Normal')}",
             "",
             "ISSUE",
             record.get("summary") or "(no summary)",
             "",
             "CUSTOMER",
             f"{record.get('customer') or 'not logged in'} (signed in, identity verified)" if record.get("customer")
             else "not logged in",
             ""]
    orders = record.get("orders") or {}
    lines.append("ORDERS (looked up by the agent this session)")
    if orders:
        for oid, o in orders.items():
            facts = ", ".join(f"{k}: {v}" for k, v in o.items())
            lines.append(f"- {oid}" + (f"  ({facts})" if facts else ""))
    else:
        lines.append("- none looked up")
    if record.get("orders_mentioned_unverified"):
        lines.append("Mentioned in the summary but not looked up (verify before acting): "
                     + ", ".join(record["orders_mentioned_unverified"]))
    if record.get("refused"):
        lines += ["", "ALREADY REFUSED BY AMI"] + [f"- {x}" for x in record["refused"]]
    if record.get("done"):
        lines += ["", "ALREADY DONE BY AMI"] + [f"- {x}" for x in record["done"]]
    lines += ["",
              "ROUTING (internal/escalation-matrix.md)",
              f"Department: {r.get('department', '')}",
              f"Contact: {r.get('contact', '')}",
              f"SLA: {r.get('sla', '')}",
              "",
              "SUGGESTED NEXT STEPS"]
    lines += [f"{i}. {step}" for i, step in enumerate(r.get("next_steps") or [], 1)]
    lines += ["", f"Trace: session {record.get('session')}  turn {record.get('turn')}"]
    return "\n".join(lines) + "\n"


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


def _jira_summary(record):
    r = record.get("routing") or {}
    cat = (r.get("category") or "general_complaint").replace("_", " ")
    oid = next(iter(record.get("orders") or {}), None) or next(iter(record.get("orders_mentioned_unverified") or []), None)
    head = f"{record['ticket']} [{cat}]" + (f" order {oid}" if oid else "")
    return (head + ": " + (record.get("summary") or "customer hand-off"))[:250]


def _jira_labels(record):
    r = record.get("routing") or {}
    labels = ["ami", r.get("category") or "general_complaint",
              "authenticated" if record.get("customer") else "guest",
              "priority-" + (r.get("priority") or "normal").lower()]
    return [re.sub(r"[^A-Za-z0-9_-]", "-", x) for x in labels]


def _jira(record):
    missing = [k for k in ("JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT")
               if not getattr(config, k, None)]
    if missing:
        raise ValueError("jira backend needs " + ", ".join(missing))
    auth = base64.b64encode(f"{config.JIRA_EMAIL}:{config.JIRA_API_TOKEN}".encode()).decode()
    payload = {"fields": {
        "project": {"key": config.JIRA_PROJECT},
        "issuetype": {"name": config.JIRA_ISSUE_TYPE or "Task"},
        "summary": _jira_summary(record),
        "labels": _jira_labels(record),
        "description": {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": ln}]} if ln else
            {"type": "paragraph", "content": []}
            for ln in _text(record).splitlines()]},
    }}
    req = urllib.request.Request(
        config.JIRA_URL.rstrip("/") + "/rest/api/3/issue",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(req, timeout=_timeout()) as resp:
        return json.loads(resp.read().decode()).get("key") or f"HTTP {resp.status}"


_JIRA_KEY = re.compile(r"^[A-Z][A-Z0-9]{1,9}-\d+$")


def jira_key(ref):
    """The issue key if `ref` came back from Jira (e.g. "AMI-2"), else None."""
    backend = (config.ESCALATION_BACKEND or "none").strip().lower()
    if backend == "jira" and isinstance(ref, str) and _JIRA_KEY.match(ref):
        return ref
    return None


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
