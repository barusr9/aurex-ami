"""S1 prefetch: the order lookup that never needed a model call.

When an authenticated customer's message names an order id, react() looks
it up BEFORE the first model call and puts it in working memory. These
tests pin the saving (one fewer model call, and the model sees the order on
its very first call) and, more importantly, that nothing about data
isolation changed: no scope -> no prefetch; someone else's order -> the same
refusal the tool always gave, nothing leaked.

Model replies are scripted with fakes.py; nothing here hits the network.
"""

import pytest

from ami import planner, tools
from ami.memory import ConversationMemory, WorkingMemory
from fakes import Reply

RAJ, MEI = "raj@example.com", "mei@example.com"
RAJ_ORDER = "112-1111111-1111111"      # raj's, delivered
MEI_ORDER = "112-3333333-3333333"      # mei's Kindle, preparing


def _brief_seen_by_model(fake_llm):
    """The working-memory note injected as the 2nd system message."""
    msgs = fake_llm.calls[0]["messages"]
    return msgs[1]["content"] if len(msgs) > 1 and msgs[1]["role"] == "system" else ""


def test_prefetch_saves_the_first_round_trip(fresh_store, fake_llm):
    fake_llm.script(Reply(content="It was delivered on the 3rd."))
    convo, work = ConversationMemory("sys"), WorkingMemory(scope=RAJ)
    convo.add_user(f"What's the status of {RAJ_ORDER}?")

    planner.react(convo, work, trace=False)

    assert len(fake_llm.calls) == 1                      # answer only — no tool round-trip
    assert RAJ_ORDER in work.orders                      # fetched before the model ran
    assert RAJ_ORDER in _brief_seen_by_model(fake_llm)   # and the model saw it on call 1
    assert "delivered" in _brief_seen_by_model(fake_llm)


def test_no_scope_means_no_prefetch(fresh_store, fake_llm):
    """Unauthenticated users keep the auth gate: nothing is looked up for them."""
    fake_llm.script(Reply(content="Please log in first."))
    convo, work = ConversationMemory("sys"), WorkingMemory(scope=None)
    convo.add_user(f"What's the status of {RAJ_ORDER}?")

    planner.react(convo, work, trace=False)

    assert work.orders == {}
    assert RAJ_ORDER not in _brief_seen_by_model(fake_llm)


def test_someone_elses_order_is_refused_not_leaked(fresh_store, fake_llm):
    """raj asks about mei's order: same 404 the tool always gave, no Kindle."""
    fake_llm.script(Reply(content="I can't find that order on your account."))
    convo, work = ConversationMemory("sys"), WorkingMemory(scope=RAJ)
    convo.add_user(f"What's in order {MEI_ORDER}?")

    planner.react(convo, work, trace=False)

    assert MEI_ORDER not in work.orders
    assert any(MEI_ORDER in f for f in work.failures)    # recorded as a refusal
    assert "kindle" not in _brief_seen_by_model(fake_llm).lower()


def test_known_order_is_not_fetched_twice(fresh_store, fake_llm, monkeypatch):
    calls = []
    real = tools.run
    monkeypatch.setattr(planner.tools, "run",
                        lambda n, a, scope=None: (calls.append(n), real(n, a, scope=scope))[1])
    fake_llm.script(Reply(content="Still delivered."))
    convo, work = ConversationMemory("sys"), WorkingMemory(scope=RAJ)
    work.record("get_order", {"order_id": RAJ_ORDER},
                tools.get_order(RAJ_ORDER, scope=RAJ))      # already known
    convo.add_user(f"Any update on {RAJ_ORDER}?")

    planner.react(convo, work, trace=False)

    assert calls.count("get_order") == 0


def test_flag_off_restores_old_behaviour(fresh_store, fake_llm, monkeypatch):
    monkeypatch.setattr(planner, "PREFETCH_ORDERS", False)
    fake_llm.script(Reply(content="ok"))
    convo, work = ConversationMemory("sys"), WorkingMemory(scope=RAJ)
    convo.add_user(f"Status of {RAJ_ORDER}?")

    planner.react(convo, work, trace=False)

    assert work.orders == {}


def test_prefetch_logs_an_event(fresh_store, fake_llm):
    from ami import observe
    fake_llm.script(Reply(content="ok"))
    convo, work = ConversationMemory("sys"), WorkingMemory(scope=RAJ)
    convo.add_user(f"Where is {RAJ_ORDER}?")

    planner.react(convo, work, trace=False)

    ev = [e for e in observe.EVENTS if e["kind"] == "prefetch"]
    assert ev and ev[-1]["order_id"] == RAJ_ORDER and ev[-1]["ok"] is True
