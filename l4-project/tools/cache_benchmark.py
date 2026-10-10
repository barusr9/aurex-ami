"""S1 answer-cache benchmark: 5 general questions x 3 asks, each a NEW conversation,
through ami.answer_cache.answer() with the real ReAct planner (same path as web.py).
Run from bhargava-code/:  .venv/bin/python ../tools/cache_benchmark.py"""
import time, warnings; warnings.filterwarnings("ignore")
from ami import agent_profile, answer_cache, observe, planner, policy
from ami.memory import ConversationMemory, WorkingMemory
from ami.query_classifier import classify_query

QUESTIONS = ["What is your return policy?", "How do refunds work for gift cards?",
             "Does a gift card balance expire?", "My package says delivered but it isn't here. What should I do?",
             "Can I change the delivery address after ordering?"]
SYSTEM = agent_profile.system_prompt() + planner.PLANNING_RULES
answer_cache.clear()
rows = []
for rnd in range(1, 4):
    for q in QUESTIONS:
        qt = classify_query(q)
        convo, work = ConversationMemory(SYSTEM), WorkingMemory(scope="demo1@cofy.ai")
        text, note = policy.check_input(q); work.turn = 1; convo.add_user(text)
        steps, seq0, t0 = [], observe.SEQ, time.perf_counter()
        def run():
            r = planner.react(convo, work, trace=False, steps=steps, extra=note)
            return r, [s["tool"] for s in steps]
        reply, hit = answer_cache.answer(text, qt, convo, work, run)
        ms = round((time.perf_counter() - t0) * 1000)
        llm = [e for e in observe.EVENTS if e.get("seq", 0) > seq0 and e["kind"] == "llm"]
        rows.append((rnd, q, qt, hit, len(llm), sum((e.get("tokens_in") or 0) + (e.get("tokens_out") or 0) for e in llm), sum(e.get("cost") or 0 for e in llm), ms))
        print(f"round {rnd}  {'HIT ' if hit else 'MISS'}  {qt:<7} calls={len(llm)}  tokens={rows[-1][5]:>6,}  cost=${rows[-1][6]:.4f}  {ms:>6}ms  {q[:48]}")
tot = lambda R, i: sum(r[i] for r in R)
first, repeat = [r for r in rows if r[0] == 1], [r for r in rows if r[0] > 1]
print(f"\nround 1 (cold):   {len(first)} asks  calls={tot(first,4)}  tokens={tot(first,5):,}  cost=${tot(first,6):.4f}  avg {tot(first,7)//len(first)} ms")
print(f"rounds 2-3:       {len(repeat)} asks  calls={tot(repeat,4)}  tokens={tot(repeat,5):,}  cost=${tot(repeat,6):.4f}  avg {tot(repeat,7)//len(repeat)} ms  hits={sum(r[3] for r in repeat)}/{len(repeat)}")
print(f"all 15 asks:      tokens={tot(rows,5):,}  cost=${tot(rows,6):.4f}   vs no cache ≈ tokens={3*tot(first,5):,} cost=${3*tot(first,6):.4f}  -> saving {100-100*tot(rows,5)//max(3*tot(first,5),1)}% tokens")
