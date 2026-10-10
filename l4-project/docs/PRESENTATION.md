# Ami readout — run-of-show (5 minutes)

For Bhargava and Shree, presenting on or before 11 October 2026. Rebuilt on 9 October to Bhargava's top-down flow (product → the ask → what we found → result by goal → what we changed → what is next), with the measurement and monitoring detail moved to an appendix.

## Files and links

| What | Where |
|---|---|
| Deck, PowerPoint (speaker notes inside) | [Ami-L4-Readout-Bhargava-Shree-2026-10-08.pptx](Ami-L4-Readout-Bhargava-Shree-2026-10-08.pptx) |
| Deck, PDF | [Ami-L4-Readout-Bhargava-Shree-2026-10-08.pdf](Ami-L4-Readout-Bhargava-Shree-2026-10-08.pdf) |
| Deck, live and editable | https://claude.ai/artifact/KMns74rheLukvPD6BzQzoW (shared by link; also exports PPTX/PDF) |
| The use-case readout (Bhargava) | https://github.com/barusr9/aurex-ami/blob/master/readout.html |
| The one-page readout | [../code/READOUT.md](../code/READOUT.md) |
| This repo: plan, logs, evidence, code snapshot | https://github.com/shreenathacc22/ami-l4-project |
| 9 October call notes and action items | https://claude.ai/code/artifact/834f528b-e282-41b0-8305-4f5d8c6e4505 |

## Run-of-show

Seven slides, 4 minutes 50 seconds, ten seconds for the hand-over. Bhargava opens with the product and the ask; Shree takes the numbers and closes. The notes under each slide carry the words.

| # | Slide | Who | Time | The one line |
|---|---|---|---|---|
| 1 | Ami, hardened | Bhargava | 0:10 | A support agent taken from a class demo towards production, measured before and after |
| 2 | The product: the class build, and Ami now | Bhargava | 0:40 | Left: no login, anyone could ask about any order. Right: "please log in", a customer sees only their own orders |
| 3 | The ask: six goals from Balaji | Bhargava | 0:40 | Six goals, one success test each; we took all six as the frame |
| 4 | What we found: the agent looked like it worked | Shree | 0:30 | Cancel/return never completed; a 502 hung a turn 14 min; nothing was measured |
| 5 | Result: before and after, goal by goal | Shree | 1:10 | Three met, three partial, and we say which and why |
| 6 | What we did, by goal and by layer | Shree | 1:00 | One card per goal: prompt, memory, planning, observability, guardrails, model |
| 7 | Where this goes next | Shree | 0:40 | Not the final product; S5 study, witnessed run, next levers per use case. Questions? |
| A1 | What did not work (six misses) | if asked | — | Cost not halved (proxy cache); 12-word cap reverted; routing not live; trimming; refusal reason; the policy-path gap |
| A2 | Prompt injection in the real chat UI | if asked | — | Evidence for goal 4: 90 s of "thinking…" vs a 14-second hand-off |
| A3 | What we would watch, and who gets paged | if asked | — | Six alerts; part of goal 2 |
| A4 | How we measured, and what the words mean | if asked | — | Frozen suites, judge audit, p50/p95/golden score/facts/retrieval/grounded in plain words |

If you run long: say slide 6 in one sentence and go to 7. Never skip the three amber rows on slide 5; the honest misses are the point of the readout.

Bhargava's narration for slides 1–3, in his words from the 9 October call: "This was our product, this is how it looked pre and post. The reason we did this was our goal, on the third slide. Because our goal was this, we looked at the problems it had, and the way we solved them is the next slide."

## Likely questions, and the answers

**Why not half the cost, as S1 asked?**
Most of each call is a fixed prompt prefix. The proxy caches it automatically but unpredictably: cache hits swung from 79% to 48% between two runs of the same suite. Tokens fell 39%; dollars fell 38% on the golden set and 11% on the behavioural suite. The answer cache halves the cost of repeated questions, but the frozen suites contain no repeats, by design. Order prefetch, the lever that moves cost and latency together, is built and waits for its live run.

**What does "golden score 0.967" mean?**
28 hand-written questions with reference answers. Each row averages four checks: facts (required words present), retrieval (the right passage was looked up), correct and grounded (a judge model, audited first, says the reply conveys the reference and every claim is backed by what was looked up). "24/28 clean" is the rows that passed every check. Appendix A4 has the one-line definitions.

**The same code scored 17/20 and 20/20. Which is right?**
Both. The three cases that flip are refusals whose wording sometimes drops the reason ("already shipped", "30-day window"). The model is non-deterministic at this temperature, so we report the range, not the best run.

**How do you know the LLM judge is trustworthy?**
We audited it before any golden run: given each case's own reference answer it scores 0.98; given an unrelated reference it scores 0.05. It tells all 28 references apart.

**Was the 14-minute hang real?**
Real, and reproducible: the proxy returns a 502 on the injection text every time, and the old code retried with hidden SDK retries stacked on its own. Re-created in the real chat UI: still "thinking…" at 90 seconds. The new code hands off in about 14 seconds (appendix A2).

**Model routing: did it do what you asked?**
The router is built, tested (7 tests) and routes 7 of 20 cases to the cheap tier, −25% computed from real prices. The class proxy serves `gpt-5.6-terra` whatever is requested, so there is no cheaper tier to switch to here. It ships switched off, and we say so. The goal is a better product, not a rule about which model answers.

**Why hasn't the user study (S5) run?**
It needs three people and a facilitator; the agent cannot run it. The kit, a reset script and a facilitator sheet are ready.

**What happens next?**
The S5 sessions, then the witnessed run of both suites on merged master (about ten minutes) that replaces the table's numbers and gets a signature, then the follow-up PR.

## Before you present

1. Open the PPTX once in PowerPoint and page through it; the speaker notes are under each slide. The PDF is the exact rendering of the live deck.
2. Have readout.html, READOUT.md and the repo open in browser tabs for questions.
3. Optional live demo (adds about 30 seconds): with the app running on port 4000, ask "what is my order id" without logging in and show the login gate; then log in as demo1 and ask "when did my AirPods arrive?".
4. Say the numbers predate the merge with master; the witnessed run on merged master is the final measurement.
