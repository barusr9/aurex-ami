"""Element 3 of the agent: PLANNING — the ReAct loop.

ReAct = Reason + Act. The agent works in a visible cycle:

    Thought:      what do I know, what do I need next, why this tool
    Action:       the tool call
    Observation:  what came back

...repeated until it has enough to answer. The baseline loop in agent.py
does the same Action/Observation dance, but the Thought is hidden inside
the model. Here we force it into the open by making "thought" a REQUIRED
argument on every tool.

That one change buys three things:
  - you can read why the agent did what it did (debugging)
  - the model plans before it acts instead of after (better tool choice)
  - a bad plan is visible in the trace, not buried in a wrong answer
"""

import json
import re
import time

from ami import observe
from ami import tools
from ami.llm import MODEL, complete
from ami.config import config

MAX_STEPS = config.MAX_STEPS

# A turn that runs past this many seconds degrades gracefully instead of
# hanging (e.g. a model that keeps asking for tools, or a slow upstream).
# 0 disables the budget. See config.TURN_BUDGET_SECONDS.
TURN_BUDGET_SECONDS = config.TURN_BUDGET_SECONDS

# What the customer hears when we stop early — a runaway loop, a blown time
# budget, or a model error we chose not to surface raw. Honest and actionable,
# never a stack trace.
DEGRADED_REPLY = ("I'm having trouble completing that right now. Let me get a "
                  "human agent to take a look — they'll follow up shortly.")

# --------------------------------------------------------------------------
# S1: prefetch — the one model call that never needed a model
# --------------------------------------------------------------------------
# On the frozen suite, 13 of 20 cases open the same way: the customer types
# an order number and the model spends a full round-trip (~1,700 input
# tokens, ~1.6 s) deciding to call get_order with it. That decision is
# deterministic, so we make it in Python: look the order up before the first
# model call and hand the result to working memory, whose brief already tells
# the model "you know this, do not look it up again". Same tool, same scope
# check, so data isolation is unchanged; an order the user may not see lands
# in work.failures exactly as it would have after the model asked.

PREFETCH_ORDERS = config.PREFETCH_ORDERS
_ORDER_ID = re.compile(r"\b\d{3}-\d{7}-\d{7}\b")


def prefetch_orders(convo, work):
    """Look up any order ids in the latest user message, if authenticated.

    Returns the ids fetched (for logging/tests). Does nothing when the user is
    not authenticated — the auth gate is the tool's, not ours to bypass — or
    when the id is already in working memory.
    """
    scope = getattr(work, "scope", None)
    if not PREFETCH_ORDERS or not scope or not convo.history:
        return []
    last = convo.history[-1]
    if last.get("role") != "user":
        return []
    fetched = []
    for oid in dict.fromkeys(_ORDER_ID.findall(last.get("content") or "")):
        if oid in work.orders:
            continue                              # brief already carries it
        result = tools.run("get_order", {"order_id": oid}, scope=scope)
        work.record("get_order", {"order_id": oid}, result)
        observe.log("prefetch", tool="get_order", order_id=oid,
                    ok="error" not in result)
        fetched.append(oid)
    return fetched

PLANNING_RULES = """
HOW YOU PLAN
Work one step at a time, and think before each step.
- Before every tool call, state your reasoning in the 'thought' argument:
  what you already know, what is still missing, and why this tool is next.
- Take ONE action at a time. Read the observation before deciding again.
- Errors come in two kinds, and they are handled differently:
  * "retry": true  -> YOU called the tool wrongly. Fix the arguments and
    call it again. Do not tell the customer about this.
  * no retry flag  -> a POLICY refusal. Never repeat the call. Tell the
    customer the rule and offer their next option.
- Stop as soon as you can answer. Do not call tools you do not need.
"""


def _schemas_with_thought():
    """Copy the tool schemas, adding a required 'thought' to each one."""
    out = []
    for schema in tools.SCHEMAS:
        fn = json.loads(json.dumps(schema["function"]))   # deep copy
        params = fn["parameters"]
        # 'thought' goes LAST, and that position was not a style choice.
        # It was first, which reads better — think, then act — and the
        # golden set said otherwise: the model filled in the thought and
        # stopped, emitting cancel_order({}) with no order_id at all. Over
        # 27 rows, 7 of 41 tool calls came back with empty arguments, each
        # one a wasted step and sometimes a wrong answer to the customer.
        # Moving one key to the end of the dict: 0 of 39.
        #
        # The model writes JSON left to right, so whatever comes first is
        # what it commits to. Put the reasoning first and the reasoning is
        # all you reliably get.
        params["properties"] = {
            **params["properties"],
            "thought": {
                "type": "string",
                "description": "Your reasoning: what you know, what you "
                               "still need, and why this tool is next.",
            },
        }
        params["required"] = params["required"] + ["thought"]
        out.append({"type": "function", "function": fn})
    return out


SCHEMAS = _schemas_with_thought()


def react(convo, work, trace=True, steps=None, extra=None, model=None):
    """Run the ReAct loop until the agent produces an answer for the customer.

    convo : ConversationMemory — what was said, sent in full to the model
    work  : WorkingMemory      — what is known, injected as a short note
    trace : print the Thought/Action/Observation trace to the terminal
    steps : optional list; each step is appended as a dict so a caller
            (the web UI) can render the trace instead of printing it
    model : which model to use this turn (S6 routing). None = the default
            MODEL, i.e. unchanged behaviour. The caller picks the tier once
            per turn (see ami/route.py) and every step uses it.
    """
    model = model or MODEL
    t0 = time.perf_counter()
    prefetch_orders(convo, work)          # S1: saves the first round-trip
    for step in range(1, MAX_STEPS + 1):
        # Time budget: stop before another model call if this turn has already
        # run too long. Checked between steps so we never abandon a call
        # mid-flight — we just decline to start the next one.
        if TURN_BUDGET_SECONDS and (time.perf_counter() - t0) > TURN_BUDGET_SECONDS:
            observe.log("degraded", reason="turn_budget_exceeded",
                        budget_s=TURN_BUDGET_SECONDS, step=step)
            return DEGRADED_REPLY

        # Working memory is re-read before EVERY step, so the agent plans
        # against what it has already established, not just the transcript.
        response = complete(convo.messages(extra_system=work.brief()),
                            tools=SCHEMAS, model=model)
        message = response.choices[0].message
        convo.add_assistant(message.model_dump(exclude_none=True))

        # No action requested -> the agent is done reasoning, this is the answer.
        if not message.tool_calls:
            return message.content

        for call in message.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            # Pull the reasoning out; it is for us, not for the tool.
            thought = args.pop("thought", "(no thought given)")
            # Thread scope through all tool calls for data isolation (CRITICAL)
            scope = getattr(work, 'scope', None)
            result = tools.run(name, args, scope=scope)
            work.record(name, args, result)      # <- the observation updates what we know

            if steps is not None:
                steps.append({"n": step, "thought": thought, "tool": name,
                              "args": args, "observation": result})

            if trace:
                arg_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
                print(f"  [{step}] Thought: {thought}")
                print(f"      Action: {name}({arg_str})")
                print(f"      Observation: {json.dumps(result)}\n")

            convo.add_observation(call.id, result)

    return ("I'm not able to sort this out myself. Let me get a human agent "
            "to take a look.")


CHAINS_OF_THOUGHT_RULES = """
HOW YOU PLAN
Break down your reasoning into clear steps before acting.
- Think through the problem step by step in your internal monologue
- Before every tool call, state your complete reasoning in the 'thought' argument:
  what you already know, what is still missing, and why this tool is next.
- Take ONE action at a time. Read the observation before deciding again.
- Errors come in two kinds, and they are handled differently:
  * "retry": true  -> YOU called the tool wrongly. Fix the arguments and
    call it again. Do not tell the customer about this.
  * no retry flag  -> a POLICY refusal. Never repeat the call. Tell the
    customer the rule and offer their next option.
- Stop as soon as you can answer. Do not call tools you do not need.
"""


def chains_of_thought(convo, work, trace=True, steps=None):
    """Run the chains-of-thought loop until the agent produces an answer.

    Chains of thought: the agent reasons through the problem step-by-step
    before making tool calls, with explicit intermediate reasoning steps.

    convo : ConversationMemory — what was said, sent in full to the model
    work  : WorkingMemory      — what is known, injected as a short note
    trace : print the Thought/Action/Observation trace to the terminal
    steps : optional list; each step is appended as a dict so a caller
            (the web UI) can render the trace instead of printing it
    """
    for step in range(1, MAX_STEPS + 1):
        # Working memory is re-read before EVERY step, so the agent plans
        # against what it has already established, not just the transcript.
        response = complete(convo.messages(extra_system=work.brief()),
                            tools=SCHEMAS)
        message = response.choices[0].message
        convo.add_assistant(message.model_dump(exclude_none=True))

        # No action requested -> the agent is done reasoning, this is the answer.
        if not message.tool_calls:
            return message.content

        for call in message.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            # Pull the reasoning out; it is for us, not for the tool.
            thought = args.pop("thought", "(no thought given)")
            # Thread scope through all tool calls for data isolation (CRITICAL)
            scope = getattr(work, 'scope', None)
            result = tools.run(name, args, scope=scope)
            work.record(name, args, result)      # <- the observation updates what we know

            if steps is not None:
                steps.append({"n": step, "thought": thought, "tool": name,
                              "args": args, "observation": result})

            if trace:
                arg_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
                print(f"  [{step}] Thought: {thought}")
                print(f"      Action: {name}({arg_str})")
                print(f"      Observation: {json.dumps(result)}\n")

            convo.add_observation(call.id, result)

    return ("I'm not able to sort this out myself. Let me get a human agent "
            "to take a look.")
