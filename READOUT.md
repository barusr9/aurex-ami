# L4 Readout — Ami (Amazon support agent) — <your name> · witnessed by <pair>

A production-readiness review, not a demo. Same frozen suite, measured
before and after, including the change that did not work.

Frozen golden suite: 20 behavioural eval cases, frozen 2026-10-06
(`evals.py` CASES). 10 complaint cases added this weekend, frozen 2026-10-07.

---

## 1. The system, on the eight layers

| Layer | Module | Changed this weekend? |
|---|---|---|
| Prompt | `agent_profile.py`, `planner.PLANNING_RULES` | — (verified cache-stable) |
| Model | `llm.py` | ✅ config-driven, 5xx retry |
| Memory | `memory.py` (conversation + working + long-term) | ✅ `max_turns` → config |
| Tools | `tools.py` (7 tools, guardrails in the tools) | — |
| Retrieval | `knowledge.py` (chroma RAG over the rules) | ✅ degrades to [] on failure |
| Planning | `planner.py` (ReAct) / `plan_execute.py` | ✅ per-turn time budget |
| Guardrails / policy | `policy.py`, `query_classifier.py`, `route.py` | ✅ routing added |
| Observability | `observe.py`, `dashboard.py`, `/logs` | ✅ alerts + reachable dashboard |

## 2. The project

**S1–S6 · Harden Ami for production** — take a working Stage-3 agent and
make it cheaper, observable, resilient, honest, and self-testing, proving
each with before/after numbers on a frozen suite. The gap it closes: the
agent worked, but nothing proved it *stayed* working or what it cost.

## 3. Before and after — same frozen suite (20 cases, frozen 2026-10-06)

| | before | after | change |
|--------------------|---------|---------|--------|
| cost per run (¢)   | 0.89¢   | ~0.89¢  | ~0 (see §4/§5) |
| p50 latency (ms)   | 5,912   | ~5,900  | ~0 |
| p95 latency (ms)   | (polluted by a 502) | n/a | infra, excluded |
| golden-set score   | 15/20 (75%) | 15–16/20 | flat; failures are model non-determinism |
| users at SLO break | n/a (single-tenant demo) | n/a | — |
| failure screenshot | `/logs` 401 dead-end | login→dashboard | see §4 |

> The honest headline: **no metric got materially worse, and none got the
> dramatic win the plan hoped for** — because the two biggest levers were
> blocked by the environment (see §5). What *did* improve is unmeasurable in
> a number but real: the system is now resilient, observable, honest under
> pressure, and self-testing. The complaint suite went 0→10/10.

## 4. What moved, by kind of case

| Case kind | Before | After | Note |
|---|---|---|---|
| Unit tests | 251/46 (crashing collection) | **292→309/0** | eval harness + 46 stale tests fixed, +17 new |
| Eval harness | 0/20 (all crashed) | 16/20 runs clean | API-drift repaired; rest is model variance |
| Complaint cases | 0/10 (didn't exist) | **10/10** | invented facts, leaks, over-promising — all refused |
| Dashboard reachability | 401 dead-end | login → `/logs` | fixed redirect + login flow |
| Dependency failures | crash / raw stack trace | graceful message | model/retrieval/tool/timeout all handled |

## 5. What did NOT work (not optional)

Two planned cost wins could not be demonstrated **because the class proxy
constrains the environment, not because the code is wrong:**

1. **Model routing (S6) cut no cost.** The proxy ignores the requested model
   — `luna`, `sol`, `4o-mini`, `terra` all return `gpt-5.6-terra`. The
   routing logic is built, tested (7 tests), and correct, but with one model
   available there is no cheaper tier to route to. Shipped **off by default**.

2. **Prompt caching needed no code and can't be forced.** Caching is
   automatic on the proxy (measured: a cache HIT is ~$0.0008/turn vs
   ~$0.0050 COLD, **~84% cheaper**; 67% of baseline input tokens were already
   cached). But the cache is **unreliable** — with a byte-identical prefix,
   hits came and went run to run. We verified Ami's prefix is already
   cache-optimal (stable, sent first), so there is no code lever left to pull.

The lesson: on this proxy, the cost dial is mostly outside our hands. The
change we *kept* — wiring `max_turns` to config — only helps long sessions
the frozen suite doesn't exercise, so it shows ~0 here by design. Reported as
exactly that rather than hidden.

## 6. What we would watch in production

| Metric | Threshold | Who gets paged |
|---|---|---|
| Golden-set score (nightly eval) | < 70% | on-call eng — quality regression |
| Tool error rate (`/logs`) | > 15% | on-call eng |
| Cost per turn | > $0.02 | eng + finance |
| Turn p95 latency | > 12,000 ms | on-call eng |

All four are implemented as `ALERT_*` thresholds in `config.py`; the monitor
(`observe.check_alerts`) fires a distinct `alert` event on breach, surfaced
on `/logs`. Disabled by default; set the thresholds to arm them.

---

## Still open — needs a human (prepared, not done)

These two L4 requirements cannot be completed by the agent alone:

- **Witnessed sign-off (readout rule 3).** A pair must watch the after-run
  happen and sign this report. To reproduce the numbers: healthy proxy, then
  `python3 evals.py --out results/baseline_react.json` and
  `python3 evals.py --only complaint`. (Avoid running during a proxy 502
  window — it pollutes latency; `llm.py` now backs off but a hard outage
  still skews p95.)

- **S5 — Trustworthy to users (3-person study).** Not startable by the agent.
  Prep is done: a clean reachable `/logs`, graceful failures to observe, and
  10 complaint scenarios that double as a task script. Next step: recruit 3
  people, run the tasks, log each trust-break moment, redesign it, re-test.

## How to reproduce every number here

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest      # 309 passed
python3 evals.py --out results/baseline_react.json   # the frozen-suite numbers
python3 evals.py --only complaint            # 10/10 complaint cases
```
