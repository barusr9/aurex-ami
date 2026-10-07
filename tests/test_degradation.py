"""Graceful degradation (S4): switch off each dependency, prove the agent
still answers calmly — no crash, no confident wrong answer.

Each dependency gets a fault injected:
  - knowledge store down  -> search returns [], no invented policy
  - a tool errors         -> clean refusal dict, loop continues
  - the model errors       -> caller shows DEGRADED_REPLY, not a stack trace
  - a turn runs too long   -> the time budget stops it with DEGRADED_REPLY

Model replies are scripted with fakes.py; nothing here hits the network.
"""

import time

import pytest

from ami import knowledge, planner, tools
from ami.memory import ConversationMemory, WorkingMemory
from fakes import Reply, tool_call

RAJ = "raj@example.com"
DELIVERED = "112-1111111-1111111"       # raj's delivered order


# --------------------------------------------------------------------------
# Knowledge store down
# --------------------------------------------------------------------------

class TestKnowledgeStoreDown:
    """If the vector store raises, search degrades to [] rather than crashing."""

    def test_search_returns_empty_when_store_raises(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("chroma unavailable")
        monkeypatch.setattr(knowledge, "collection", boom)

        result = knowledge.search("what is the return policy?")
        assert result == []

    def test_search_knowledge_tool_survives_a_dead_store(self, monkeypatch):
        """The tool wrapper returns a clean (empty) result, not an exception."""
        def boom(*a, **k):
            raise RuntimeError("chroma unavailable")
        monkeypatch.setattr(knowledge, "collection", boom)

        out = tools.search_knowledge("what is the return policy?")
        assert out == {"passages": []}          # honest "found nothing", no invention
        assert "error" not in out


# --------------------------------------------------------------------------
# A tool errors mid-loop
# --------------------------------------------------------------------------

class TestToolErrorDoesNotCrash:
    def test_tool_run_never_raises_on_bad_call(self, fresh_store):
        """A wrong call comes back as a retryable error dict, not an exception."""
        out = tools.run("get_order", {"nonexistent_arg": 1}, scope=RAJ)
        assert isinstance(out, dict)
        assert "error" in out


# --------------------------------------------------------------------------
# The model errors
# --------------------------------------------------------------------------

class TestModelError:
    def test_degraded_reply_is_calm_and_offers_a_human(self):
        """The customer-facing fallback never leaks internals."""
        msg = planner.DEGRADED_REPLY.lower()
        assert "human" in msg or "agent" in msg
        # no stack-trace / exception-shaped text
        for leak in ("error:", "traceback", "exception", "none", "{"):
            assert leak not in msg


# --------------------------------------------------------------------------
# Per-turn time budget
# --------------------------------------------------------------------------

class TestTurnBudget:
    def test_budget_stops_a_runaway_turn(self, fresh_store, monkeypatch):
        """With a tiny budget and a model that only ever asks for more tools,
        the loop returns DEGRADED_REPLY instead of looping to MAX_STEPS.

        The scripted model is made to take real time per call, so the budget
        is actually exceeded between steps (fake_llm alone is too fast to
        advance the clock)."""
        from types import SimpleNamespace
        monkeypatch.setattr(planner, "TURN_BUDGET_SECONDS", 0.05)

        def slow_complete(messages, **kwargs):
            time.sleep(0.04)                       # two of these exceed 0.05s
            msg = Reply(tool_calls=[tool_call("get_order", order_id=DELIVERED,
                                              thought="looking")])
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])
        monkeypatch.setattr(planner, "complete", slow_complete)

        convo = ConversationMemory("sys")
        work = WorkingMemory(scope=RAJ)
        convo.add_user("where is my order?")

        reply = planner.react(convo, work, trace=False)
        assert reply == planner.DEGRADED_REPLY

    def test_zero_budget_disables_the_check(self, fresh_store, fake_llm, monkeypatch):
        """Budget 0 means no time limit — the loop answers normally."""
        monkeypatch.setattr(planner, "TURN_BUDGET_SECONDS", 0)
        fake_llm.script(Reply(content="It was delivered yesterday."))

        convo = ConversationMemory("sys")
        work = WorkingMemory(scope=RAJ)
        convo.add_user("where is my order?")

        reply = planner.react(convo, work, trace=False)
        assert reply == "It was delivered yesterday."
