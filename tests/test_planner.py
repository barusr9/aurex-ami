"""Planner: the ReAct loop in ami/planner.py.

Pins two things. First, the tool schemas the planner sends carry a required
`thought` argument, and it is the LAST property, which the README records
as the difference between 7 empty tool calls in 41 and none. Second, the
loop itself: a reply ends it, a tool call runs the tool with `thought`
stripped, each observation goes back into the conversation and into
working memory, and MAX_STEPS ends a loop that never answers.

Every model reply is scripted with fakes.py, so nothing here calls the model.
"""

from ami import planner, store, tools
from ami.memory import ConversationMemory, WorkingMemory
from fakes import Reply, tool_call

DELIVERED = "112-1111111-1111111"          # raj@example.com, delivered


# --------------------------------------------------------------------------
# The schemas the planner sends
# --------------------------------------------------------------------------

def test_every_schema_requires_a_thought():
    for schema in planner.SCHEMAS:
        params = schema["function"]["parameters"]
        assert "thought" in params["properties"]
        assert "thought" in params["required"]


def test_thought_is_the_last_property_in_every_schema():
    for schema in planner.SCHEMAS:
        keys = list(schema["function"]["parameters"]["properties"])
        assert keys[-1] == "thought", schema["function"]["name"]


def test_planner_keeps_one_schema_per_tool():
    assert len(planner.SCHEMAS) == len(tools.SCHEMAS)
    assert [s["function"]["name"] for s in planner.SCHEMAS] == \
           [s["function"]["name"] for s in tools.SCHEMAS]


def test_planner_does_not_change_the_original_tool_schemas():
    for schema in tools.SCHEMAS:
        assert "thought" not in schema["function"]["parameters"]["properties"]


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------

def test_react_returns_the_reply_when_the_model_calls_no_tool(fake_llm):
    fake_llm.script(Reply(content="Happy to help."))
    convo, work = ConversationMemory("system"), WorkingMemory()

    assert planner.react(convo, work, trace=False) == "Happy to help."
    assert convo.messages()[-1] == {"role": "assistant", "content": "Happy to help."}


def test_react_sends_the_thought_schemas_and_the_working_memory_brief(fake_llm):
    fake_llm.script(Reply(content="ok"))
    convo, work = ConversationMemory("system"), WorkingMemory()
    convo.add_user("where is my order?")
    expected = convo.messages(extra_system=work.brief())

    planner.react(convo, work, trace=False)

    call = fake_llm.calls[0]
    assert call["tools"] is planner.SCHEMAS
    assert call["messages"] == expected


def test_react_runs_the_tool_and_keeps_the_thought_out_of_its_arguments(fake_llm, fresh_store):
    fake_llm.script(
        Reply(tool_calls=[tool_call("get_order", order_id=DELIVERED,
                                    thought="I need the order first")]),
        Reply(content="It was delivered."),
    )
    convo, work, steps = ConversationMemory("system"), WorkingMemory(), []

    result = planner.react(convo, work, trace=False, steps=steps)

    assert result == "It was delivered."
    assert steps == [{
        "n": 1,
        "thought": "I need the order first",
        "tool": "get_order",
        "args": {"order_id": DELIVERED},
        "observation": tools.run("get_order", {"order_id": DELIVERED}),
    }]


def test_react_puts_the_observation_back_into_the_conversation(fake_llm, fresh_store):
    fake_llm.script(
        Reply(tool_calls=[tool_call("get_order", order_id=DELIVERED, thought="t")]),
        Reply(content="done"),
    )
    # react threads work.scope into every tool call for data isolation, so the
    # reader must be authenticated as the order's owner for get_order to return
    # the order (and not an "authentication required" error).
    convo, work = ConversationMemory("system"), WorkingMemory(scope="raj@example.com")

    planner.react(convo, work, trace=False)

    observation = convo.messages()[-2]
    assert observation["role"] == "tool"
    assert observation["tool_call_id"] == "call_get_order"
    assert DELIVERED in observation["content"]


def test_react_updates_working_memory_from_the_observation(fake_llm, fresh_store):
    fake_llm.script(
        Reply(tool_calls=[tool_call("get_order", order_id=DELIVERED, thought="t")]),
        Reply(content="done"),
    )
    convo, work = ConversationMemory("system"), WorkingMemory()

    planner.react(convo, work, trace=False)

    assert DELIVERED in work.brief()


def test_react_treats_unreadable_arguments_as_an_empty_call(fake_llm, fresh_store):
    broken = tool_call("get_order")
    broken.function.arguments = "not json"
    fake_llm.script(Reply(tool_calls=[broken]), Reply(content="sorry"))
    convo, work, steps = ConversationMemory("system"), WorkingMemory(), []

    assert planner.react(convo, work, trace=False, steps=steps) == "sorry"
    assert steps[0]["args"] == {}
    assert steps[0]["thought"] == "(no thought given)"
    assert steps[0]["observation"]["retry"] is True       # a mistake, not a refusal


def test_react_gives_up_after_max_steps(fake_llm, fresh_store):
    looping = Reply(tool_calls=[tool_call("get_order", order_id=DELIVERED, thought="again")])
    fake_llm.script(*[looping] * planner.MAX_STEPS)
    convo, work, steps = ConversationMemory("system"), WorkingMemory(), []

    result = planner.react(convo, work, trace=False, steps=steps)

    assert result.startswith("I'm not able to sort this out")
    assert len(steps) == planner.MAX_STEPS
    assert len(fake_llm.calls) == planner.MAX_STEPS


def test_react_prints_the_trace_only_when_asked(fake_llm, fresh_store, capsys):
    step = Reply(tool_calls=[tool_call("get_order", order_id=DELIVERED, thought="look it up")])

    fake_llm.script(step, Reply(content="done"))
    planner.react(ConversationMemory("s"), WorkingMemory(), trace=True)
    out = capsys.readouterr().out
    assert "[1] Thought: look it up" in out
    assert f"Action: get_order(order_id={DELIVERED!r})" in out
    assert "Observation:" in out

    fake_llm.script(step, Reply(content="done"))
    planner.react(ConversationMemory("s"), WorkingMemory(), trace=False)
    assert capsys.readouterr().out == ""


# --------------------------------------------------------------------------
# Phase 1 fixes (2026-10-07): policy dispatch, degrade, notes
# --------------------------------------------------------------------------

CANCELLABLE = "112-3333333-3333333"        # mei@example.com, preparing


def test_react_cancel_completes_across_two_turns(fake_llm, fresh_store):
    """The cancel flow works end to end: preview on turn 1, the customer's
    yes on turn 2, the order is cancelled. It used to be impossible —
    react called tools.run directly and the schema had no `confirmed`."""
    convo, work = ConversationMemory("system"), WorkingMemory(scope="mei@example.com")
    work.turn = 1
    fake_llm.script(Reply(tool_calls=[tool_call("cancel_order", order_id=CANCELLABLE, thought="t")]),
                    Reply(content="Confirm?"))
    planner.react(convo, work, trace=False)
    assert store.ORDERS[CANCELLABLE]["status"] == "preparing"

    work.turn = 2
    fake_llm.script(Reply(tool_calls=[tool_call("cancel_order", order_id=CANCELLABLE,
                                                confirmed="yes", thought="t")]),
                    Reply(content="Done."))
    planner.react(convo, work, trace=False)
    assert store.ORDERS[CANCELLABLE]["status"] == "cancelled"


def test_react_cannot_confirm_in_the_same_turn(fake_llm, fresh_store):
    convo, work = ConversationMemory("system"), WorkingMemory(scope="mei@example.com")
    work.turn = 1
    fake_llm.script(Reply(tool_calls=[tool_call("cancel_order", order_id=CANCELLABLE, thought="t")]),
                    Reply(tool_calls=[tool_call("cancel_order", order_id=CANCELLABLE,
                                                confirmed="yes", thought="t")]),
                    Reply(content="Please confirm."))
    planner.react(convo, work, trace=False)
    assert store.ORDERS[CANCELLABLE]["status"] == "preparing"


def test_react_degrades_when_the_model_call_fails(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("502 Bad gateway")
    monkeypatch.setattr(planner, "complete", boom)
    reply = planner.react(ConversationMemory("s"), WorkingMemory(), trace=False)
    assert reply == planner.DEGRADED_REPLY


def test_react_sends_the_policy_note_to_the_model(fake_llm):
    fake_llm.script(Reply(content="ok"))
    convo = ConversationMemory("system")
    convo.add_user("hi")
    planner.react(convo, WorkingMemory(), trace=False, extra="NOTE: card removed")
    sent = fake_llm.calls[0]["messages"]
    assert any("NOTE: card removed" in (m.get("content") or "") for m in sent
               if m["role"] == "system")
