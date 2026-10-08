"""answer_cache: repeated general first questions are answered without the model,
and nothing account-specific, failed or stale is ever served from it."""

import pytest

from ami import answer_cache, planner
from ami.memory import ConversationMemory, WorkingMemory


@pytest.fixture(autouse=True)
def empty_cache(monkeypatch):
    answer_cache.clear()
    monkeypatch.setattr(answer_cache, "_knowledge_stamp", lambda: "docs-v1")
    yield
    answer_cache.clear()


def _turn(text, query_type="PUBLIC", reply="Returns: 30 days.", tools=("search_knowledge",), convo=None):
    convo = convo or ConversationMemory("s")
    convo.add_user(text)
    calls = []
    def run():
        calls.append(1)
        convo.add_assistant({"role": "assistant", "content": reply})
        return reply, list(tools)
    out, hit = answer_cache.answer(text, query_type, convo, WorkingMemory(), run)
    return out, hit, len(calls), convo


def test_second_identical_question_skips_the_model():
    _turn("What is your return policy?")
    out, hit, model_runs, convo = _turn("what is your RETURN policy")     # normalised match
    assert hit and model_runs == 0 and out == "Returns: 30 days."
    assert convo.history[-1] == {"role": "assistant", "content": "Returns: 30 days."}


def test_private_questions_are_never_cached():
    _turn("where is my order", query_type="PRIVATE")
    assert _turn("where is my order", query_type="PRIVATE")[2] == 1


def test_turns_that_used_order_tools_are_not_cached():
    _turn("what is the status", tools=("search_knowledge", "get_order"))
    assert _turn("what is the status")[2] == 1


def test_only_the_first_message_of_a_conversation_is_cached():
    convo = ConversationMemory("s")
    convo.add_user("hi"); convo.add_assistant({"role": "assistant", "content": "hello"})
    _turn("What is your return policy?", convo=convo)                    # second message: not stored
    assert _turn("What is your return policy?")[2] == 1


def test_failure_replies_are_never_cached():
    _turn("What is your return policy?", reply=planner.DEGRADED_REPLY, tools=())
    assert _turn("What is your return policy?")[2] == 1


def test_editing_the_knowledge_invalidates_the_cache(monkeypatch):
    _turn("What is your return policy?")
    monkeypatch.setattr(answer_cache, "_knowledge_stamp", lambda: "docs-v2")
    assert _turn("What is your return policy?")[2] == 1


def test_entries_expire(monkeypatch):
    _turn("What is your return policy?")
    monkeypatch.setattr(answer_cache, "TTL_SECONDS", -1)
    assert _turn("What is your return policy?")[2] == 1
