"""Ticket routing from internal/escalation-matrix.md, and the richer ticket.

Tests pin:
- the matrix file parses into rows with triggers, department, contact, steps
- the summary selects the row; unknown issues fall to general_complaint
- order facts become the first, concrete next step
- the matrix is outside knowledge/ (never indexed for customer answers)
- policy passes verified order facts to escalate and drops model-supplied context
- the ticket text carries issue, orders, routing and numbered next steps
"""

from types import SimpleNamespace

import pytest

from ami import ROOT, escalations, policy, routing, tools
from ami.memory import WorkingMemory

LATE = {"111-2222222-2222222": {"item": "MacBook Air M3 Case", "status": "shipped", "eta": "2026-10-13"}}


def test_matrix_parses():
    rows = routing.load_matrix()
    cats = [r["category"] for r in rows]
    assert {"delivery_delay", "damaged_or_wrong_item", "returns_refunds", "cancellation",
            "account_access", "payment_billing", "general_complaint"} <= set(cats)
    for r in rows:
        assert r["department"] and r["contact"] and r["next_steps"]


def test_matrix_is_not_customer_searchable():
    assert routing.MATRIX.parent.name == "internal"
    assert not str(routing.MATRIX).startswith(str(ROOT / "knowledge"))


@pytest.mark.parametrize("summary,category", [
    ("order is late and customer is upset", "delivery_delay"),
    ("package never arrived", "delivery_delay"),
    ("item arrived broken", "damaged_or_wrong_item"),
    ("wants a refund", "returns_refunds"),
    ("wants to cancel the order", "cancellation"),
    ("charged twice on the card", "payment_billing"),
    ("cannot log in to the account", "account_access"),
    ("customer is just very unhappy", "general_complaint"),
])
def test_summary_selects_the_row(summary, category):
    assert routing.route(summary)["category"] == category


def test_order_facts_become_the_first_step():
    r = routing.route("order is late", LATE)
    assert r["next_steps"][0].startswith("Start from order 111-2222222-2222222")
    assert "ETA 2026-10-13" in r["next_steps"][0]
    assert r["department"] == "Logistics & Fulfilment"


def test_missing_matrix_falls_back(tmp_path):
    r = routing.route("anything", path=tmp_path / "nope.md")
    assert r["category"] == "general_complaint" and r["next_steps"]


def test_policy_passes_verified_orders_and_drops_model_context():
    w = WorkingMemory(scope="raj@example.com")
    w.orders = dict(LATE)
    seen = {}
    real = tools.run
    def spy(name, args, scope=None):
        seen.update(args); return {"escalated": True, "ticket": "ESC-1", "message": "m", "summary": "s"}
    tools.run = spy
    try:
        policy.guarded_run("escalate", {"summary": "late", "context": {"orders": {"999-9999999-9999999": {}}}}, w)
    finally:
        tools.run = real
    assert set(seen["context"]["orders"]) == {"111-2222222-2222222"}
    assert seen["context"]["orders"]["111-2222222-2222222"]["eta"] == "2026-10-13"


def test_ticket_text_has_issue_orders_routing_and_steps(monkeypatch):
    rec = escalations.open_ticket("Customer says order 111-2222222-2222222 is late",
                                  customer="demo1@cofy.ai", context={"orders": LATE})
    t = escalations._text(rec)
    for part in ("ISSUE", "ORDERS", "111-2222222-2222222", "MacBook Air M3 Case", "ROUTING",
                 "Logistics & Fulfilment", "SUGGESTED NEXT STEPS", "1. Start from order"):
        assert part in t, part
    assert escalations._jira_summary(rec).startswith(rec["ticket"] + " [delivery delay] order 111-2222222-2222222")
    assert set(escalations._jira_labels(rec)) >= {"ami", "delivery_delay", "authenticated", "priority-high"}


def test_order_mentioned_but_not_looked_up_is_flagged():
    rec = escalations.open_ticket("problem with 112-3333333-3333333", customer="demo1@cofy.ai")
    assert rec["orders"] == {}
    assert rec["orders_mentioned_unverified"] == ["112-3333333-3333333"]
    assert "verify before acting" in escalations._text(rec)
