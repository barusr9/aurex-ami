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
    lines = [_jira_summary(record), _headline(record),
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


def _category_title(record):
    r = record.get("routing") or {}
    return (r.get("category") or "general_complaint").replace("_", " ").capitalize()


def _headline(record):
    """One sentence: ticket, category, order, and the agent's summary."""
    oid = next(iter(record.get("orders") or {}), None) or next(iter(record.get("orders_mentioned_unverified") or []), None)
    head = f"{record['ticket']} [{_category_title(record).lower()}]" + (f" order {oid}" if oid else "")
    return head + ": " + (record.get("summary") or "customer hand-off")


def _jira_summary(record):
    """Jira title is the ESC ticket number the customer was given."""
    return record["ticket"]


def _adf(record):
    """The ticket as Atlassian Document Format: headings, bold names, lists."""
    r = record.get("routing") or {}
    t = lambda text, bold=False: ({"type": "text", "text": text, **({"marks": [{"type": "strong"}]} if bold else {})})
    para = lambda *parts: {"type": "paragraph", "content": [p for p in parts if p.get("text")]}
    head = lambda text: {"type": "heading", "attrs": {"level": 3}, "content": [t(text)]}
    items = lambda kind, rows: {"type": kind, "content": [
        {"type": "listItem", "content": [para(*row) if isinstance(row, tuple) else para(t(row))]} for row in rows]}

    doc = [para(t(_headline(record), bold=True)),
           head("Issue"), para(t(record.get("summary") or "(no summary)")),
           head("Customer"),
           para(t(record["customer"], bold=True), t("  (signed in, identity verified)")) if record.get("customer")
           else para(t("not logged in"))]

    orders = record.get("orders") or {}
    doc.append(head("Orders"))
    if orders:
        rows = []
        for oid, o in orders.items():
            facts = ", ".join(f"{k}: {v}" for k, v in o.items())
            rows.append((t(oid, bold=True), t(f"  {facts}" if facts else "")))
        doc.append(items("bulletList", rows))
    else:
        doc.append(para(t("None looked up by the agent this session.")))
    if record.get("orders_mentioned_unverified"):
        doc.append(para(t("Mentioned but not looked up, verify before acting: ", bold=True),
                        t(", ".join(record["orders_mentioned_unverified"]))))
    if record.get("refused"):
        doc += [head("Already refused by Ami"), items("bulletList", record["refused"])]
    if record.get("done"):
        doc += [head("Already done by Ami"), items("bulletList", record["done"])]

    contact = r.get("contact") or ""
    name, _, email = contact.partition(",")
    doc += [head("Routing"),
            para(t("Department: "), t(r.get("department") or "", bold=True)),
            para(t("Contact: "), t(name.strip(), bold=True), t(f", {email.strip()}" if email else "")),
            para(t("SLA: "), t(r.get("sla") or "")),
            head("Suggested next steps"),
            items("orderedList", r.get("next_steps") or ["Read the conversation and reply within the SLA"]),
            para(t(f"Trace: session {record.get('session')}, turn {record.get('turn')}. "
                   "Routing from internal/escalation-matrix.md."))]
    return {"type": "doc", "version": 1, "content": doc}


def _jira_labels(record):
    r = record.get("routing") or {}
    labels = [r.get("category") or "general_complaint",
              "authenticated" if record.get("customer") else "guest",
              "priority-" + (r.get("priority") or "normal").lower()]
    return [re.sub(r"[^A-Za-z0-9_-]", "-", x) for x in labels]


def _due_date(sla, today=None):
    """Due date (YYYY-MM-DD) from an SLA like '4 business hours' or '1 business day'.
    Hours are due the same business day; days count business days forward."""
    import datetime as _dt
    d = today or _dt.date.today()
    def next_business(x):
        while x.weekday() >= 5:
            x += _dt.timedelta(days=1)
        return x
    d = next_business(d)
    m = re.search(r"(\d+)\s*business\s*day", sla or "", re.I)
    for _ in range(int(m.group(1)) if m else 0):
        d = next_business(d + _dt.timedelta(days=1))
    return d.isoformat()


_JIRA_FIELDS = {}          # cache: project key -> {lower-case field name: field id}
_PRIORITY_MAP = {"high": "High", "normal": "Medium", "medium": "Medium", "low": "Low",
                 "highest": "Highest", "lowest": "Lowest"}


def _jira_request(path, auth, data=None, method="GET"):
    req = urllib.request.Request(
        config.JIRA_URL.rstrip("/") + path, method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(req, timeout=_timeout()) as resp:
        body = resp.read().decode()
        return resp.status, (json.loads(body) if body else {})


def _jira_field_ids(auth):
    """Field name -> id for a Task in the project, looked up once per process.
    Lets a Jira admin add Priority / Department / Order number / Customer email
    in the UI without anyone copying field ids into config. Never raises."""
    key = config.JIRA_PROJECT
    if key in _JIRA_FIELDS:
        return _JIRA_FIELDS[key]
    ids = {}
    try:
        _, types = _jira_request(f"/rest/api/3/issue/createmeta/{key}/issuetypes", auth)
        want = (config.JIRA_ISSUE_TYPE or "Task").lower()
        tid = next(t["id"] for t in types.get("issueTypes", []) if t["name"].lower() == want)
        _, meta = _jira_request(f"/rest/api/3/issue/createmeta/{key}/issuetypes/{tid}", auth)
        ids = {f["name"].strip().lower(): f["fieldId"] for f in meta.get("fields", [])}
    except Exception:
        ids = {}
    _JIRA_FIELDS[key] = ids
    return ids


def _jira_extra_fields(record, ids):
    """Values for the optional fields this project has. Missing ones are skipped."""
    r = record.get("routing") or {}
    out = {}
    if "priority" in ids:
        out["priority"] = {"name": _PRIORITY_MAP.get((r.get("priority") or "normal").lower(), "Medium")}
    oid = next(iter(record.get("orders") or {}), None)
    if oid and "order number" in ids:
        out[ids["order number"]] = oid
    if record.get("customer") and "customer email" in ids:
        out[ids["customer email"]] = record["customer"]
    if r.get("department") and "department" in ids:
        out[ids["department"]] = r["department"]
    if "start date" in ids:                      # the day the hand-off happened
        import datetime as _dt
        out[ids["start date"]] = _dt.date.fromtimestamp(record.get("ts") or __import__("time").time()).isoformat()
    return out


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
        "duedate": _due_date((record.get("routing") or {}).get("sla")),
        "description": _adf(record),
    }}
    ids = _jira_field_ids(auth)
    extra = _jira_extra_fields(record, ids)
    payload["fields"].update(extra)
    if "priority" in extra:                      # the real field replaces the label
        payload["fields"]["labels"] = [l for l in payload["fields"]["labels"] if not l.startswith("priority-")]
    status, body = _jira_request("/rest/api/3/issue", auth, data=payload, method="POST")
    return body.get("key") or f"HTTP {status}"


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
