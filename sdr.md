# Ami — Software Development Requirements (SDR)

The engineering spec for the six business requirements in `brd.md`. Each
section (S1–S6) is the "how" for the matching BRD item (the "what/why"),
grounded in a baseline taken 2026-10-06 from the live `/logs` trace.

> **Status (2026-10-07).** Foundation + all six items implemented and on
> `fix/logs-login-redirect` (PR #1); see `READOUT.md` for the graded review.
> - **S0 eval integrity** ✅ harness runs, suite 309/0, baseline committed
> - **S1 cost** ✅ measured (caching ~84% when it hits, but unreliable +
>   proxy-limited — see READOUT §5); `max_turns` config-wired
> - **S2 monitor** ✅ `check_alerts` + `/logs` surfacing + break-on-purpose test
> - **S4 graceful** ✅ model/retrieval/tool/timeout all degrade; fault tests
> - **S6 routing** ✅ built + tested, OFF by default (proxy serves one model)
> - **S3 complaints** ✅ 10 cases, 10/10 pass
> - **Config hygiene** ✅ model/agent/alert knobs centralized
> - **Human-only, prepared not done:** S5 user study, witnessed sign-off

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

> **Foundation — S0 (eval integrity) — DONE.** S1, S2, S3, S6 all need a
> working eval harness to prove "same quality / before-and-after." It was
> broken (`evals.py` crashed 0/20 on API drift; 46 unit tests stale); it is
> now repaired in this branch — evals run end-to-end and the unit suite is
> 292/0. This unblocks the fourth readout number (golden-set score).
>
> **Tasks (S0):**
> - [x] Fix `evals.py` planner/scope/spy drift — harness runs
> - [x] Retry transient 5xx (502/503/504) in `llm.py`
> - [x] Fix all 46 stale unit tests → 292 passed / 0 failed
> - [x] Document run process in README (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`)
> - [ ] Record a committed eval baseline to `results/` (the "before" score)

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
| Quality | no golden-set score regression |
| Proof | before/after cost + latency shown in `/logs` |

**Tasks**
- [x] Probe whether the proxy honors prompt caching (no-code measurement)
      → **YES**: caching is automatic, warms after ~3 calls, then ~100% of
      the stable prefix is cached (billed at the cheaper cached-in rate,
      ~10× cheaper: $0.20 vs $2.00 /M for gpt-5.6-terra).
- [ ] Maximize cache hits: keep the stable system prompt + tool schemas as a
      byte-identical prefix; ensure volatile working-memory (`work.brief()`)
      is injected AFTER it (already the case in `memory.messages()` — verify
      and lock in). Consider pinning tool-schema order.
- [ ] Record before/after cost + p50 on the frozen suite
- [ ] (If needed) trim/cap history — only after S0 proves no score regression
- [ ] Capture one reverted attempt with numbers (feeds readout §5)

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

**Tasks**
- [ ] Define the quality metric (reuse S0 eval pass rate / a canary subset)
- [ ] Add a threshold check → distinct `alert` event in `observe.py`
- [ ] Surface the alert on `/logs`
- [ ] Break-on-purpose demo: degrade the agent, show the monitor catches it

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

**Tasks**
- [ ] Pull 10 real complaints/bad answers (from `/feedback` or authored)
- [ ] Encode each as a golden/eval case that fails today
- [ ] Fix each in prompt/tool/policy
- [ ] Show before(fail)→after(pass) for all 10 via the harness
- [ ] Mark these as "added this weekend, frozen `<date>`" (readout rule 1)

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

**Tasks**
- [x] Retry transient gateway 5xx in `llm.py` (done in R6)
- [ ] Graceful fallback on non-retryable model error/timeout (offer escalate)
- [ ] Handle knowledge store down → honest "can't look that up", no invention
- [ ] Enforce a per-turn time/step budget; log overflow as a distinct event
- [ ] Fault-injection test per dependency (model, search, tool)
- [ ] Capture before/after failure screenshots (feeds readout §4 / presentation)

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

**Tasks**
- [ ] Recruit 3 participants; define the real tasks they'll attempt
- [ ] Run sessions; log the moment each stopped trusting it
- [ ] Redesign each trust-break moment
- [ ] Re-test: confirm the moment no longer breaks trust

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

**Tasks**
- [ ] Extend `query_classifier.py` with a difficulty signal (simple vs. complex)
- [ ] Route simple/PUBLIC → cheap tier; complex/multi-tool/guardrail → strong
- [ ] Log the model choice per turn in the trace
- [ ] Measure blended $/turn + golden-set score vs. single-model baseline
- [ ] Move thresholds into `config.py`/env
- [ ] Strong candidate for readout §5: if routing drops score, revert + report

---

## Supporting work (not a BRD item, but required)

| Item | Why | Status |
|---|---|---|
| **Eval integrity (S0)** | Measuring stick for S1/S2/S3/S6 | **Mostly done** — evals run; unit suite 292/0; run docs added. Remaining: commit a baseline to `results/` |
| **Config hygiene** | S1/S4/S6 knobs must be tunable | Open — `MODEL`, `MAX_STEPS`, per-turn budget, routing thresholds should read from `config.py`/env |

## Dependency order

| Step | Item | Why now |
|---|---|---|
| 1 | Eval integrity (S0) ✅ | Nothing's "same quality" / "before-after" is provable without it — **done** |
| 2 | S1 (cost) ← next | Biggest win; caching can start in parallel (billing-only) |
| 3 | S6 (routing) | Needs S1's clean baseline |
| 4 | S3 (complaints→tests) | Builds on the working eval harness |
| 5 | S2 (regression monitor) | Reuses the eval signal from S0/S3 |
| 6 | S4 (graceful) | Independent; slot anytime |
| 7 | S5 (trust study) | Human study; after behavior stabilizes |

---

## Output Expected (L4 Readout deliverables)

The project is graded as a **production-readiness review, not a demo** — the
same frozen suite, measured before and after, witnessed, including the change
that did not work. Concretely, we must produce:

**1. `READOUT.md` — a one-page the reviewer can act on**, with six parts:

| # | Part | Content |
|---|---|---|
| 1 | The system, on the eight layers | one line per layer; mark the layers changed this weekend |
| 2 | The project | `S<n> · <title>` — the gap it closes, in one sentence |
| 3 | Before & after | same frozen suite (`<N>` cases, frozen `<date>`); the table below |
| 4 | What moved, by kind of case | which case types got better, worse, or did not move |
| 5 | What did NOT work | at least one change tried and reverted, **with its numbers** |
| 6 | What you'd watch in production | the metric, the threshold, and who gets paged |

**2. The four numbers — before and after, on the same frozen suite:**

| Metric | Baseline (before) | After | Rule |
|---|---|---|---|
| Cost per run (¢) | 1.06¢/turn | _tbd_ | — |
| p50 latency (ms) | 4,960 | _tbd_ | — |
| p95 latency (ms) | 5,480 | _tbd_ | — |
| Golden-set score | _tbd (R6 now makes this measurable)_ | _tbd_ | hiding a number that got worse fails the readout outright |

Plus the two supporting rows from the readout table: **users at SLO break**,
and a **failure screenshot** (before/after links).

**3. At least one reverted change (§5 is mandatory).** Keep a change we tried
that made a number worse, revert it, and report it with its numbers — e.g.
"routing simple turns to the cheap tier cut cost X% but dropped golden-set
score Y points, so we reverted it." A weekend where every change worked is a
weekend where somebody stopped measuring.

**4. Witnessed.** A pair watches the after-run happen and signs the report —
evidence the numbers came from the system, today.

**5. The five-minute presentation, in order:** gap (30s) → change (1m) →
table (2m, read the row that got *worse* out loud) → failure (1m) → watch
(30s).

> Mapping to our work: S1 fills the cost + latency rows; **R6 (done) makes the
> golden-set *score* row measurable** — it is the fourth number, not optional;
> S2 is the "what you'd watch in production" metric + alert; S3 grows the
> frozen suite from real complaints; S4 produces the failure screenshots; S6
> is a prime candidate for the mandatory §5 reverted change.
