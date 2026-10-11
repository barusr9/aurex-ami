"""Returns, cancellations and system failures open back-office tickets.

Tests pin:
- a confirmed return opens a 'return' ticket whose id is the RMA, routed to Returns & Refunds
- a return whose reason sounds like damage routes to Returns & Quality instead
- a confirmed cancellation opens a CXL-<n> 'cancellation' ticket routed to Order Management
- a degraded turn for a signed-in customer opens one 'system-failure' ESC ticket
  and counts as the conversation's escalation; guests get none
- the type label leads the Jira labels
- ticket failures never change the customer's tool result
"""

import pytest

from ami import escalations, planner, store, tools
from ami.memory import WorkingMemory


def _lines():
    import json
    if not escalations.FILE.exists():
        return []
    return [json.loads(l) for l in escalations.FILE.read_text().splitlines() if l.strip()]


def _opened(kind):
    return [r for r in _lines() if r.get("status") == "opened" and r.get("kind") == kind]


def _own_delivered_order():
    for oid, o in store.ORDERS.items():
        if o["status"] == "delivered":
            return oid, o["email"]
    pytest.skip("no delivered order in the seed store")


def _own_cancellable_order():
    for oid, o in store.ORDERS.items():
        if o["status"] in ("preparing", "processing", "ordered"):
            return oid, o["email"]
    pytest.skip("no cancellable order in the seed store")


def test_return_opens_ticket_with_rma(fresh_store):
    oid, email = _own_delivered_order()
    r = tools.start_return(oid, "unclear music sound", scope=email, confirmed=True)
    assert r["rma"].startswith("RMA-")
    [t] = _opened("return")
    assert t["ticket"] == r["rma"]
    assert t["routing"]["department"] == "Returns & Refunds"
    assert oid in t["orders"] and t["customer"] == email
    assert escalations._jira_labels(t)[0] == "return"


def test_damaged_return_routes_to_quality(fresh_store):
    oid, email = _own_delivered_order()
    tools.start_return(oid, "arrived broken", scope=email, confirmed=True)
    [t] = _opened("return")
    assert t["routing"]["category"] == "damaged_or_wrong_item"
    assert t["routing"]["department"] == "Returns & Quality"


def test_cancellation_opens_cxl_ticket(fresh_store):
    oid, email = _own_cancellable_order()
    r = tools.cancel_order(oid, scope=email, confirmed=True)
    assert r["cancelled"] is True
    [t] = _opened("cancellation")
    assert t["ticket"].startswith("CXL-")
    assert t["routing"]["department"] == "Order Management"
    assert escalations._jira_labels(t)[0] == "cancellation"


def test_preview_without_confirmation_opens_nothing(fresh_store):
    oid, email = _own_delivered_order()
    tools.start_return(oid, "changed my mind", scope=email, confirmed=False)
    assert _lines() == []


def test_system_failure_ticket_once_and_counts_as_escalation():
    w = WorkingMemory(scope="raj@example.com")
    planner._promise_followup(w, "model or gateway error (APIError)")
    planner._promise_followup(w, "model or gateway error (APIError)")     # second failure, same chat
    tickets = _opened("system-failure")
    assert len(tickets) == 1 and tickets[0]["ticket"].startswith("ESC-")
    assert w.escalation == tickets[0]["ticket"]
    assert tickets[0]["routing"]["department"] == "Customer Care"


def test_guest_failure_opens_nothing():
    planner._promise_followup(WorkingMemory(), "model error")
    assert _opened("system-failure") == []


def test_ticket_failure_never_changes_the_tool_result(fresh_store, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(escalations, "open_ticket", boom)
    oid, email = _own_delivered_order()
    r = tools.start_return(oid, "too small", scope=email, confirmed=True)
    assert r["rma"].startswith("RMA-") and "error" not in r


def test_rma_numbers_continue_after_a_restart(fresh_store, monkeypatch):
    """The demo store resets on restart; RMA numbering must not."""
    oid, email = _own_delivered_order()
    first = tools.start_return(oid, "too small", scope=email, confirmed=True)["rma"]
    store.RETURNS.clear()                                   # simulate a restart
    store.ORDERS[oid]["status"] = "delivered"
    second = tools.start_return(oid, "too small", scope=email, confirmed=True)["rma"]
    assert first != second
