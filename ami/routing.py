"""Ticket routing: which department handles a hand-off, and what to do next.

The rules live in internal/escalation-matrix.md (a markdown table a support
lead can edit), not in code. route() picks a row from the agent's summary and
the order facts the agent actually looked up, and returns the department,
contact, priority, SLA and next steps to put on the ticket.

The matrix sits outside knowledge/ on purpose: knowledge/ is indexed for
customer answers, and internal contacts must never be retrievable by a customer.
"""

import re

from ami import ROOT

MATRIX = ROOT / "internal" / "escalation-matrix.md"
DEFAULT_CATEGORY = "general_complaint"

_FALLBACK = {
    "category": DEFAULT_CATEGORY, "triggers": [], "department": "Customer Care",
    "contact": "care@ami.example", "priority": "Normal", "sla": "1 business day",
    "next_steps": ["Read the conversation and the agent's summary",
                   "Reply to the customer within the SLA"],
}


def load_matrix(path=None):
    """Rows of the matrix table as dicts, in file order. Never raises."""
    try:
        text = (path or MATRIX).read_text()
    except OSError:
        return [_FALLBACK]
    rows, header = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            header = [c.lower().replace(" ", "_") for c in cells]
            continue
        if set("".join(cells)) <= set("-: "):
            continue                                  # the |---|---| separator row
        r = dict(zip(header, cells))
        trig = r.get("triggers", "")
        rows.append({
            "category": r.get("category", DEFAULT_CATEGORY),
            "triggers": [] if "(default)" in trig else [t.strip().lower() for t in trig.split(",") if t.strip()],
            "department": r.get("department", ""), "contact": r.get("contact", ""),
            "priority": r.get("priority", "Normal"), "sla": r.get("sla", ""),
            "next_steps": [s.strip() for s in r.get("next_steps", "").split(";") if s.strip()],
        })
    return rows or [_FALLBACK]


def _row(rows, category):
    return next((r for r in rows if r["category"] == category), None)


def route(summary, orders=None, path=None):
    """Pick the matrix row for this hand-off. Returns a copy of the row with
    `orders` (the facts the ticket should show) and order-specific steps."""
    rows = load_matrix(path)
    text = (summary or "").lower()
    orders = orders or {}

    chosen = None
    for r in rows:                                    # first trigger match wins
        if any(re.search(r"\b" + re.escape(t) + r"\b", text) for t in r["triggers"]):
            chosen = r
            break
    if chosen is None:
        chosen = _row(rows, DEFAULT_CATEGORY) or rows[-1]

    out = dict(chosen, next_steps=list(chosen["next_steps"]))
    step = _order_step(orders)
    if step:
        out["next_steps"].insert(0, step)
    out["orders"] = orders
    return out


def _order_step(orders):
    """'Start from order X, item, status, ETA' for the first order looked up."""
    for oid, o in (orders or {}).items():
        bits = [f"order {oid}"]
        if o.get("item"):
            bits.append(o["item"])
        if o.get("status"):
            bits.append(f"status {o['status']}")
        if o.get("eta"):
            bits.append(f"ETA {o['eta']}")
        if o.get("delivered_on"):
            bits.append(f"delivered {o['delivered_on']}")
        return "Start from " + ", ".join(bits)
    return None


def route_category(category, orders=None, path=None):
    """The matrix row for a known category (returns, cancellations, failures),
    with the same order-specific first step as route(). None if not in the matrix."""
    row = _row(load_matrix(path), category)
    if row is None:
        return None
    out = dict(row, next_steps=list(row["next_steps"]), orders=orders or {})
    step = _order_step(orders)
    if step:
        out["next_steps"].insert(0, step)
    return out

