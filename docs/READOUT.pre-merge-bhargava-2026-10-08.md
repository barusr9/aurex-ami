# Production-readiness readout — Ami (Amazon support agent)

**Author:** <your name> · **Witness:** <pair> · **Date:** 2026-10-07

Rule of this readout: the same frozen 20-case suite, measured before and after, including what did not work. Anything not measured live is marked **unproven**.

---

## 1. The system, on the 8 layers

| Layer | What it is in Ami | Changed this weekend? |
|---|---|---|
| Prompt | System prompt + planning rules | — |
| Model | LLM client (config-driven, retry on 5xx) | **Changed** |
| Memory | Conversation + working + long-term memory | **Changed** |
| Tools | Order lookup, tracking, cancel, return, auth | — |
| Retrieval | RAG over the policy/knowledge base | **Changed** |
| Planning | ReAct loop with a per-turn budget | **Changed** |
| Guardrails / Policy | Refusals, data-leak checks, model routing | **Changed** |
| Observability | Event log, `/logs` dashboard, threshold alerts | **Changed** |

6 of 8 layers changed. Prompt and Tools were left alone on purpose: the frozen suite grades behaviour, and changing the prompt would have made before/after incomparable.

## 2. The project

Ami already worked (Stage 3: lookups, tracking, cancels, returns, policy answers, auth, guardrails). The gap this weekend closes: **nothing proved it stayed working, degraded safely, or what it cost** — so we hardened it against six production requirements and tried to prove each with before/after numbers.

| Req | Requirement | Status | Evidence |
|---|---|---|---|
| S1 | Cheaper/faster, same quality. **Cheaper** = classify the input and send simple questions to a cheap model, hard ones to a strong one (the same routing S6 builds). **Faster** = a live status line in the chat saying what Ami is doing. | **In progress** | Cheaper: routing built, 7 tests; projected −25% ($0.1774 → $0.1334), short of the "under half" target and **unproven live** (see §5). Transcript trimming proven safe as a second lever (3 tests). Faster: **not built** — the chat still shows a static "thinking…" bubble. A status line changes how fast the wait feels; it does not move the p50/p95 in §3. |
| S2 | Catch it when it breaks | **Completed** | `check_alerts` thresholds, surfaced on `/logs`, proven with a break-on-purpose test. 4 tests. |
| S3 | Learn from complaints | **Completed** | 10 complaint cases authored; 10/10 pass. |
| S4 | Fail gracefully | **Completed** | Model timeout, dead knowledge store, tool error, runaway turns all degrade to "let me get a human". 6 fault-injection tests. |
| S5 | Trustworthy to users (3-person study) | **In progress** | Study kit written; human sessions **not run**. |
| S6 | Right model per job | **Completed (logic)** | Routing built, 7 tests. Saving computed, not measured live: −25% on the frozen suite ($0.1774 → $0.1334). See §5. |

Scope: 32 files changed, +4,069 / −225 lines. 3 new modules (routing, config, complaint handling), ~460 test lines, and edits to the model, memory, retrieval, planning, guardrails and observability layers.

## 3. Before and after — same 20-case frozen suite, two independent runs

| Metric | Before | After | Delta |
|---|---|---|---|
| Cost per turn | 0.89¢ | 1.05¢ | **+18% (worse)** |
| p50 latency | 5,912 ms | 7,083 ms | **+20% (worse)** |
| p95 latency | 17,897 ms | 15,217 ms | −15% (better) |
| Behavioural quality score | 15/20 (75%) | 15/20 (75%) | flat |
| Golden-set score (28 cases, grades what it *said*) | — (not run) | **16/28 clean (57%)**, mean 0.83 | first measurement |

**Honest note on the two worse rows.** Cost and p50 went up by roughly a fifth. We believe this is measurement noise, not a regression, for one specific reason: on identical cases (same prompt, same code), **8 of 20 cases swung more than 1.5× between the two runs, in both directions**. The cause is the proxy's prompt cache, which hits or misses unpredictably run to run, and a hit is ~84% cheaper than a miss. Our changes add no per-turn cost: routing is off by default, and degradation paths only execute on failure.

That said, "we believe" is not "we measured". With two runs we cannot separate a small real regression from cache noise. What we can say with confidence is that the **quality score held flat at 75%** and p95 did not get worse. A third and fourth run, once the token budget resets, is the only way to close this.

## 4. What moved, by kind of case

| Kind of case | Before | After |
|---|---|---|
| Unit tests | 251 passing / 46 failing | **312 passing / 0 failing** (fixed a broken eval harness + 46 stale tests, added ~60 new) |
| Eval harness | 0/20 — crashed | runs clean |
| Complaint handling | 0 cases | **10/10 pass** (refuses to invent facts, leak other customers' data, over-promise, or cave to pressure) |
| Dashboard | unreachable — 401 error | login flow fixed, reachable |
| Dependency failures | crashed / leaked stack traces | graceful "let me get a human" messages |
| Golden-set grader | 0/28 — the grader could not see react's tool calls (retrieval 0.00 on every row while the trace showed 19 lookups) | **16/28 (57%)** after fixing the harness; grounded 0.25 → 0.95. The 12 that still fail are real: 3 answer missing-package questions without looking up the policy, 4 omit a detail the reference requires, 5 are the same non-deterministic cases the behavioural suite shows |

None of these show up in the four numbers in §3. They are the reason the four numbers can now be trusted at all: before this weekend the harness that produces them did not run.

## 5. What did NOT work (mandatory)

**(a) Model routing (S6) could not run live.** The class proxy serves one model regardless of the model requested, so there is nothing to switch to in this environment. The routing logic is built and tested (7 tests), and the saving is computed from real per-model prices on the frozen suite's actual token counts: $0.1774 → $0.1334, −25%, if the easy cases went to a 10× cheaper model. That number is **a projection, not a measurement**. It becomes real the day Ami points at a multi-model endpoint; until then S6 is "logic complete, benefit unproven".

**(b) S1 is unproven on both halves.** *Cheaper:* S1's cost lever is the routing in (a), so it inherits the same block: the proxy serves one model, the −25% is a projection, and even if it lands it is short of the "under half" target. The direct measurement we planned instead (trimming on, same suite) never ran because the API key's token budget (3M tokens) ran out. The irony is not lost on us: the budget was drained by the eval runs themselves, which send fat input tokens on every turn — exactly the waste S1 was built to cut. Trimming is proven *safe* (3 tests), not proven *cheaper*. *Faster:* the status line is not built. When it is, it will not move p50 or p95; it is a perceived-speed change, and the right place to prove it is the S5 user study (does the person stop trusting Ami during the wait?), not the latency table. S1 stays **In progress / unproven**.

Also not done: the S5 three-person trust study. The kit is ready; no humans have used it yet.

## 6. What we'd watch in production

| Signal | Threshold | Who gets paged |
|---|---|---|
| Golden-set score (nightly eval) | < 70% | engineering |
| Tool error rate | > 15% | engineering |
| Cost per turn | > $0.02 | engineering + finance |
| p95 turn latency | > 12,000 ms | engineering |

Implemented as `check_alerts` thresholds; each breach writes a distinct alert event that surfaces on `/logs`.

One flag: today's measured p95 is 15,217 ms, already above the 12,000 ms line. This alert would fire on day one. Either latency comes down or the threshold gets revisited before go-live; we are not quietly raising the line to make it pass.

---

## 5-minute presentation script

**0:00–0:30 — The gap.**
"Ami worked. It could look up orders, track, cancel, return, answer policy, with auth and guardrails. What it couldn't do was prove it stayed working, fail safely, or tell us what it cost. Six production requirements, S1 to S6, one weekend, before/after numbers on a frozen 20-case suite."

**0:30–1:30 — The change.**
"Six of eight layers touched: model, memory, retrieval, planning, guardrails, observability. Prompt and tools deliberately untouched so before and after stay comparable. Thirty-two files, about four thousand lines added. Three new modules: routing, config, complaint handling. Status: S2, S3, S4 complete and tested. S6 logic complete but not runnable live. S1 and S5 in progress. I'll come back to the ones that aren't done."

**1:30–3:30 — The table. Read the worse rows out loud.**
"Same suite, two independent runs. Cost per turn: 0.89 cents before, 1.05 cents after. That is 18 percent worse. p50 latency: 5,912 milliseconds before, 7,083 after. Twenty percent worse. p95: 17,897 down to 15,217, better. Quality score: 15 of 20 before, 15 of 20 after. Flat."

"Why do I think the two worse rows are noise and not a regression? On identical cases, same prompt, same code, 8 of the 20 swung more than one and a half times between runs, in both directions. The proxy's prompt cache hits or misses unpredictably and a hit is 84 percent cheaper. Our changes add no per-turn cost. But I want to be precise: that is a belief with a mechanism behind it, not a measurement. Two runs can't separate a small real regression from cache noise. What I can stand behind is that quality held at 75 percent and p95 didn't get worse."

"Underneath those four numbers: unit tests went from 251 passing and 46 failing to 312 passing and zero failing. The eval harness went from crashing on all 20 cases to running clean. Complaint handling went from zero cases to 10 of 10. The dashboard went from a 401 to reachable. Dependency failures went from stack traces to a calm handoff to a human."

**3:30–4:30 — What did not work.**
"Two misses. First, model routing: the proxy serves one model no matter what you ask for, so I can't switch models live here. The routing is built, seven tests, and the computed saving is 25 percent on this suite, 17.7 cents to 13.3 cents. That is a projection. I have not measured it. Second, S1. Cheaper for us means routing, so it's blocked by the same single-model proxy, and 25 percent is short of the under-half target anyway. The direct measurement, trimming on, same suite, never ran because the API key's 3 million token budget ran out. It was drained by the eval runs themselves, sending fat input tokens every turn, which is exactly the problem S1 was meant to fix. Trimming is proven safe, 3 tests. It is not proven cheaper. Faster for us means a status line in the chat saying what Ami is doing. It isn't built yet, and when it is, it won't change p50. It changes how the wait feels, which is a trust question for the S5 study. Also not done: the three-person trust study for S5. Kit's written, nobody has sat down with it yet."

**4:30–5:00 — What we'd watch.**
"Four alerts. Golden-set score under 70 percent pages engineering. Tool error rate over 15 percent pages engineering. Cost per turn over two cents pages engineering and finance. p95 over 12 seconds pages engineering. And one honest footnote: today's p95 is already above that last line, so that alert would fire on day one. That's the point of setting it."

---

*Reproduce: `pytest` for the unit counts; `python3 evals.py` for the frozen-suite numbers; `python3 evals.py --only complaint` for the 10 complaint cases. Both eval commands need a key with budget.*
