"""The guest golden set, graded at the front-door gate (no model calls).

guest_eval.py grades the same set end to end against a running server."""

import json
from pathlib import Path

import pytest

from ami import query_classifier as qc

CASES = json.loads((Path(__file__).parent.parent / "guest_golden.json").read_text())


def gate(q):
    if qc.is_handoff_request(q):
        return "handoff"
    return "login" if qc.needs_login_upfront(q) else "agent"


@pytest.mark.parametrize("c", [c for c in CASES if c["expect"] == "answer"], ids=lambda c: c["q"])
def test_general_questions_are_never_gated(c):
    assert gate(c["q"]) == "agent"


@pytest.mark.parametrize("c", [c for c in CASES if c.get("upfront")], ids=lambda c: c["q"])
def test_plain_account_references_are_gated_up_front(c):
    assert gate(c["q"]) == "login"


@pytest.mark.parametrize("c", [c for c in CASES if c.get("handoff")], ids=lambda c: c["q"])
def test_handoff_requests_are_gated(c):
    assert gate(c["q"]) == "handoff"


def test_set_covers_answers_gate_agent_and_handoff():
    kinds = {c["expect"] for c in CASES}
    assert kinds == {"answer", "login"}
    assert any(c.get("upfront") is False for c in CASES)    # cases left to the agent
    assert any(c.get("handoff") for c in CASES)
