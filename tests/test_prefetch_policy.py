"""Goal 3: ground delivery/account problems in the written policy.

Three golden rows failed because the customer described a SITUATION ("says
delivered but I don't have it") and the model answered from memory instead
of looking the policy up. Now a narrow trigger prefetches search_knowledge
before the first model call and working memory carries the passage.

These pin: the lookup happens before the model runs and the model sees the
passage on its first call; it works without login (policy is public); plain
order questions do NOT trigger it (the frozen guard/cancel flows stay
untouched); passages dedupe and cap; the flag turns it off; persistence.

Retrieval is stubbed so no index is built; nothing here hits the network.
"""

import pytest

from ami import knowledge, planner
from ami.memory import WorkingMemory, ConversationMemory
from fakes import Reply

MISSING = {"heading": "Shipping and delivery — Late or missing packages",
           "source": "policies/shipping.md", "category": "policies", "score": 0.81,
           "text": "If tracking shows delivered but the customer has not found it: ask them to "
                   "check with neighbours and wait 24 hours. If still missing after 24 hours "
                   "we replace or refund at the customer's choice."}


@pytest.fixture
def stub_search(monkeypatch):
    calls = []
    def fake(question, k=3, category=None):
        calls.append(question)
        return [MISSING]
    monkeypatch.setattr(knowledge, "search", fake)
    return calls


def _brief(fake_llm):
    msgs = fake_llm.calls[0]["messages"]
    return msgs[1]["content"] if len(msgs) > 1 and msgs[1]["role"] == "system" else ""


def test_situation_is_looked_up_before_the_first_model_call(fresh_store, fake_llm, stub_search):
    fake_llm.script(Reply(content="Please wait 24 hours, then we replace or refund."))
    convo, work = ConversationMemory("sys"), WorkingMemory(scope="raj@example.com")
    convo.add_user("Tracking says my package was delivered but I don't have it.")

    planner.react(convo, work, trace=False)

    assert stub_search, "search_knowledge was never called"
    assert len(fake_llm.calls) == 1                       # no tool round-trip needed
    assert work.passages and work.passages[0]["heading"] == MISSING["heading"]
    b = _brief(fake_llm)
    assert "POLICY YOU ALREADY LOOKED UP" in b and "24 hours" in b   # model saw it on call 1


def test_policy_is_public_so_no_login_needed(fresh_store, fake_llm, stub_search):
    fake_llm.script(Reply(content="ok"))
    convo, work = ConversationMemory("sys"), WorkingMemory(scope=None)
    convo.add_user("My tracking hasn't updated in a week. What happens now?")

    planner.react(convo, work, trace=False)

    assert work.passages                                  # fetched without a scope


def test_address_change_triggers_the_lookup(fresh_store, fake_llm, stub_search):
    fake_llm.script(Reply(content="ok"))
    convo, work = ConversationMemory("sys"), WorkingMemory(scope="mei@example.com")
    convo.add_user("Can you change the delivery address on order 112-3333333-3333333?")

    planner.react(convo, work, trace=False)

    assert stub_search and "address" in stub_search[0]


@pytest.mark.parametrize("text", [
    "What's the status of 112-1111111-1111111?",
    "Cancel order 112-3333333-3333333",
    "I want to return order 112-3333333-3333333",
    "Where is order 112-2222222-2222222?",
])
def test_plain_order_actions_do_not_trigger(fresh_store, fake_llm, stub_search, text):
    """The frozen guard/cancel/return flows must be untouched by this change."""
    fake_llm.script(Reply(content="ok"))
    convo, work = ConversationMemory("sys"), WorkingMemory(scope="raj@example.com")
    convo.add_user(text)

    planner.react(convo, work, trace=False)

    assert stub_search == [] and work.passages == []


def test_passages_dedupe_and_cap_at_four():
    work = WorkingMemory()
    hit = {"source": "s", "category": "policies", "policy": "Same heading", "text": "t"}
    work.record("search_knowledge", {"question": "q"}, {"passages": [hit, hit]})
    assert len(work.passages) == 1
    many = [{"source": "s", "category": "c", "policy": f"H{i}", "text": "t"} for i in range(6)]
    work.record("search_knowledge", {"question": "q2"}, {"passages": many})
    assert len(work.passages) == 4


def test_flag_off_restores_old_behaviour(fresh_store, fake_llm, stub_search, monkeypatch):
    monkeypatch.setattr(planner, "PREFETCH_POLICY", False)
    fake_llm.script(Reply(content="ok"))
    convo, work = ConversationMemory("sys"), WorkingMemory()
    convo.add_user("My package is missing.")

    planner.react(convo, work, trace=False)

    assert stub_search == [] and work.passages == []


def test_passages_round_trip_through_persistence():
    work = WorkingMemory(scope="raj@example.com")
    work.record("search_knowledge", {"question": "q"},
                {"passages": [{"source": "s", "category": "policies", "policy": "H", "text": "t"}]})
    again = WorkingMemory.from_dict(work.to_dict())
    assert again.passages == work.passages
    assert "POLICY YOU ALREADY LOOKED UP" in again.brief()
