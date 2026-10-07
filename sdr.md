# Ami — Software Development Requirements (SDR)

The engineering spec for the six business requirements in `brd.md`. Each
section (S1–S6) is the "how" for the matching BRD item (the "what/why"),
grounded in a baseline taken 2026-10-06 from the live `/logs` trace.

## Baseline (this session: 7 real turns, logged-in demo1)

| Metric | Value | Note |
|---|---|---|
| Model served | `gpt-5.6-terra-2026-07-09` | `.env` requests `gpt-4o-mini`; proxy overrides it — see S6 |
| Total cost | $0.0745 | over 7 turns |
| Cost / turn | $0.0106 | the number that scales with a support queue |
| Tokens in / out | 44,778 / 1,186 | **37.8 : 1** — input-heavy |
| Turn latency p50 / p95 | 4,960 ms / 5,480 ms | |
| Model call p50 | 1,653 ms | |
| Model calls | 17 for 7 turns | ReAct re-sends whole transcript each step |

## Map to BRD

| SDR | BRD item | Theme | Needs working evals? |
|---|---|---|---|
| S1 | 1 | Cheaper & faster, same quality | For trim/cap approaches |
| S2 | 2 | Catch it when it breaks (regression monitor) | Yes |
| S3 | 3 | Learn from complaints (10 → test cases) | Yes (this builds them) |
| S4 | 4 | Fail gracefully | No |
| S5 | 5 | Trustworthy to users | No (human study) |
| S6 | 6 | Right model for each job | Yes |

> **Foundation — S0 (eval integrity).** S1, S2, S3, S6 all need a working
> eval harness to prove "same quality / before-and-after." It is currently
> broken (`evals.py` crashed 0/20 on an API-drift bug; 46 unit tests stale).
> The harness is being repaired in this branch; finishing it is the
> prerequisite for the items marked "needs evals" above.

---

## S1 — Make it cheaper and faster (BRD #1)

**Goal:** same quality at **under half the cost**; show cost and response
time before and after.

| | |
|---|---|
| **Problem** | ReAct resends the full, growing transcript each step ("3 msgs in" → "33 msgs in"), so input tokens are ~97% of cost (37.8:1). |

**Approaches**

| # | Approach | Changes | Quality risk | Win |
|---|---|---|---|---|
| 1 | Prompt caching on stable prefix (system + tool schemas + knowledge) | Billing only | None | Large |
| 2 | Trim / summarize old turns before resend | Behavior | High (forgetting) | Medium–large |
| 3 | Cap resent history via `MAX_CONVERSATION_TURNS` | Behavior | Medium | Medium |

**Satisfied when**

| Criterion | Target |
|---|---|
| Cost / turn | **< 50% of baseline** ($0.0106 → < $0.0053) |
| Turn latency p50 | improves vs. baseline |
| Quality | no eval-pass-rate regression |
| Proof | before/after cost + latency shown in `/logs` |

---

## S2 — Catch it when it breaks (BRD #2)

**Goal:** a simple monitor that notices when answers get worse; break it on
purpose and show the monitor catches it.

| | |
|---|---|
| **Problem** | `observe.py` tracks cost/latency/errors, but nothing watches *answer quality* over time, and nothing alerts on regression. |

**Satisfied when**

| Criterion | Target |
|---|---|
| Quality signal | a metric that drops when answers degrade (eval pass rate, refusal rate, or a canary set) |
| Alert | threshold breach surfaces on `/logs` or is logged as a distinct event |
| Proof-by-breakage | deliberately degrade the agent (e.g. swap a weaker model / corrupt a prompt) → monitor flags it |

---

## S3 — Learn from complaints (BRD #3)

**Goal:** turn **10** real complaints / bad answers into test cases, fix them,
and show before/after on those 10.

| | |
|---|---|
| **Problem** | Feedback is captured (`web.py` `/feedback` → `feedback_analysis.py`), but corrections aren't converted into regression tests; `golden.json` doesn't grow from real failures. |

**Satisfied when**

| Criterion | Target |
|---|---|
| Corpus | 10 real bad answers encoded as eval/golden cases |
| Fix | each of the 10 addressed in prompt/tool/policy |
| Proof | before (fails) → after (passes) shown for all 10, via the eval harness |

---

## S4 — Fail gracefully (BRD #4)

**Goal:** switch off each dependency (model, search, a tool) and show what the
user sees — no crashes, no confident wrong answers.

| | |
|---|---|
| **Problem** | 429 backoff exists (`llm.py`) and runaway tool loops escalate (`agent.py`), but a model timeout/5xx or a dead knowledge store raises and kills the turn. No per-turn budget. |

**Satisfied when**

| Dependency killed | User sees |
|---|---|
| Model (timeout/5xx) | graceful message / offer to escalate — not a 500 |
| Knowledge search down | honest "can't look that up right now", no invented policy |
| A tool errors | clean refusal, no confident wrong claim |
| (all) | per-turn budget enforced; each path has a fault-injection test |

---

## S5 — Make it trustworthy to users (BRD #5)

**Goal:** 3 people use it, note where each stopped trusting it, redesign that
moment, test again.

| | |
|---|---|
| **Problem** | No usability signal on *where trust breaks* (a hedge, a wrong confident claim, a slow turn, an unexplained refusal). |

**Satisfied when**

| Criterion | Target |
|---|---|
| Study | 3 participants, real tasks, trust-break moments logged |
| Redesign | each identified moment changed (copy, confirmation, latency, transparency) |
| Re-test | the same moment no longer breaks trust on a second pass |

---

## S6 — Use the right model for each job (BRD #6)

**Goal:** easy questions → cheaper model, hard ones → stronger model; show cost
against quality.

| | |
|---|---|
| **Problem** | One model for every turn. `query_classifier.py` already splits PUBLIC/PRIVATE for auth — the same signal + difficulty can route. `.env` MODEL is ignored by the proxy, so routing works on what's actually served. |

**Satisfied when**

| Criterion | Target |
|---|---|
| Routing | simple/PUBLIC → cheaper tier; complex/multi-tool → capable model; choice logged per turn |
| Cost vs. quality | blended $/turn drops with no quality regression on routed-cheap cases |
| Safety | guardrail cases stay on the strong model |
| Form | config-driven thresholds, not hardcoded |

---

## Supporting work (not a BRD item, but required)

| Item | Why | Satisfied when |
|---|---|---|
| **Eval integrity (S0)** | Measuring stick for S1/S2/S3/S6 | `evals.py` runs green; baseline in `results/`; 46 stale unit tests fixed; run docs incl. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` |
| **Config hygiene** | S1/S4/S6 knobs must be tunable | `MODEL`, `MAX_STEPS`, per-turn budget, routing thresholds read from `config.py`/env |

## Dependency order

| Step | Item | Why now |
|---|---|---|
| 1 | Eval integrity (S0) | Nothing's "same quality" / "before-after" is provable without it |
| 2 | S1 (cost) | Biggest win; caching can start in parallel (billing-only) |
| 3 | S6 (routing) | Needs S1's clean baseline |
| 4 | S3 (complaints→tests) | Builds on the working eval harness |
| 5 | S2 (regression monitor) | Reuses the eval signal from S0/S3 |
| 6 | S4 (graceful) | Independent; slot anytime |
| 7 | S5 (trust study) | Human study; after behavior stabilizes |
