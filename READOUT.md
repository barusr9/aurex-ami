# L4 Readout — Ami (Amazon support agent) — Bhargava & Shree · witnessed by <pair — sign below>

A production-readiness review, not a demo. Same frozen suites, measured
before and after, including the change that did not work.

**Frozen suites**
- **Behavioural evals** — 20 cases (`evals.py` CASES), grade what the agent *did* (right tool, correct refusal, store state). Frozen 2026-10-06.
- **Golden set** — 28 cases (`golden.json`, unchanged since 2026-10-06), grade what the agent *said*: facts + retrieval (deterministic) + an LLM judge for correct/grounded. The judge was audited first: it tells all 28 references apart from unrelated ones; its own references score 0.98.
- **Complaint cases** — 10 cases added this weekend, frozen 2026-10-07, reported separately.

"Before" = commit `cd098e0` (baseline). "After" = commit `858e9aa` (branch `fix/s1-and-eval-failures`). All runs: `gpt-5.6-terra` via the class proxy, 2026-10-08.

> **Merge note (2026-10-08):** this branch was then merged with `master` at `1b04d45` (Bhargava's S1 order prefetch, armed S2 alert defaults, evals `--exclude`, harness fix `69d6b89`). The numbers below were measured **before** that merge; the witnessed run on the merged branch (`../tools/phase4_runs.sh`) is the final measurement and replaces them.

---

## 1. The system, on the eight layers

| Layer | Module | Changed this weekend? |
|---|---|---|
| Prompt | `agent_profile.py`, `planner.PLANNING_RULES` | ✅ rewritten compact (−37% prefix); refusal-reason + policy-first rules |
| Model | `llm.py` | ✅ config-driven; 5xx retry with budgets; total per-call time limit; no hidden SDK retries |
| Memory | `memory.py` (conversation + working + long-term) | ✅ `max_turns` → config; confirmation previews not recorded as actions |
| Tools | `tools.py` (7 tools, guardrails in the tools) | ✅ eligibility checked before confirmation; `confirmed` in schema |
| Retrieval | `knowledge.py` (chroma RAG over the rules) | ✅ degrades to [] on failure |
| Planning | `planner.py` (ReAct) / `plan_execute.py` | ✅ every tool call goes through the policy layer; degrades on model error; per-turn time budget |
| Guardrails / policy | `policy.py`, `query_classifier.py`, `route.py` | ✅ cross-turn confirmation actually enforced; routing added (off by default) |
| Observability / cost | `observe.py`, `dashboard.py`, `/logs`, `answer_cache.py` | ✅ alerts; reachable dashboard; answer cache |

## 2. The project

**S1–S6 · Harden Ami for production** — make the working agent cheaper, observable, resilient, honest and self-testing, and prove each change with before/after numbers on frozen suites. The gap it closes: the agent appeared to work, but cancel/return could never complete, a bad gateway response hung a turn for 14 minutes, and nothing measured what it cost or whether it stayed correct.

## 3. Before and after — same frozen suites

| | before (`cd098e0`) | after (`858e9aa`) | change |
|---|---|---|---|
| **Golden-set score** (28 cases) | 0.805 · 16/28 clean | **0.967 · 24/28 clean** | **+0.16 · +8 cases** ✅ |
| Golden — agent cost per run | $0.224 | **$0.139** | **−38%** ✅ |
| Golden — p50 / p95 per case | 4,738 / 13,008 ms | 4,104 / 12,086 ms | −13% / −7% ✅ |
| **Behavioural score** (20 cases) | 15/20 (75%) | **17/20 (85%)** · 20/20 in a second run of the same code | +2 to +5 ✅ |
| Behavioural — cost per case (¢) | 0.89¢ | **0.79¢** | −11% |
| Behavioural — p50 / p95 (ms) | 5,912 / 17,897 | **5,293 / 13,842** | −10% / −23% ✅ |
| Tokens per behavioural run | not recorded | 80,959 (Phase 1 code: 132,803) | **−39%** vs Phase 1 |
| Complaint cases (10, frozen 10-07) | 0/10 (didn't exist) | **10/10** | ✅ |
| Repeated general questions (cache benchmark) | ~39.8k tokens / 15 asks | **18.6k (−54%)**; a hit takes 1–2 ms, 0 model calls | ✅ |
| Users at SLO break | n/a (single-tenant demo) | n/a | — |
| Failure screenshot | injection case: 14-min hang, then crash | graceful handoff in ≤15 s | ✅ `docs/evidence/injection-before-10082026.png` (still "thinking…" at 90 s) · `docs/evidence/injection-after-10082026.png` (handoff reply at 14.2 s) |

> **Read this row out loud:** S1's target was *under half the cost at the same quality*. Quality went **up**; cost fell **38%** on the golden set and **11%** on the behavioural suite — **not half**. Most of each call is a prompt prefix the proxy caches unpredictably (cache hits swung 79% → 48% between runs of the same suite), so dollars move less than tokens. Tokens fell 39%; the answer cache halves the cost of repeated questions, but the frozen suites contain no repeats.

> **Run-to-run variance is real.** The same code scored 20/20 and 17/20 on the behavioural suite in two runs on the same day. The three cases that flip are refusals whose wording sometimes drops the reason ("already shipped", "30-day window"). We report the range, not the best run.

## 4. What moved, by kind of case

| Case kind | Before | After | Note |
|---|---|---|---|
| Cancel / return with confirmation | never completed | completes after a "yes" in a later turn | ReAct bypassed the policy layer; `confirmed` was not in the schema |
| Account lookups | ✅ | ✅ | find-by-email cases now log in as the customer they name (harness) |
| Guardrail refusals (shipped / past window) | refused, reason sometimes missing | refused before any confirmation prompt; reason still dropped in ~half the runs | the one kind that **did not reliably improve** |
| Prompt injection | 14-min hang → crash (gateway 502 on that text) | graceful handoff in ≤15 s | separate gateway retry budget |
| Policy / regulation questions | 0.71 retrieval | 0.93 retrieval | "answer policy first, then ask for an order number" |
| Card number pasted | scrubbed in evals; **reached the model in the web app** | scrubbed before it enters memory | `web.py` stored the text before `check_input` |
| Stalled model connection | turn hangs indefinitely | abandoned after 60 s, one retry, graceful reply | SDK timeout is per read, not per request |
| Unit tests | 251 passed / 46 failed | **332 passed / 0 failed** | |

## 5. What did NOT work (not optional)

1. **Capping the ReAct "thought" at 12 words — reverted.** Output is billed at 6× input, and tool-call turns averaged ~97 output tokens. The cap cut output cost 13% ($0.087 → $0.076 per run) but the behavioural suite fell **20/20 → 16/20**: `guard: authority claim` *called start_return* for a "store manager" override, and a confirmed cancel never passed `confirmed=yes`. Less room to reason before acting made tool choices worse. Commit `d07e8d3`, reverted in `81b0cf5`.
2. **Model routing (S6) cut no cost live.** The proxy serves `gpt-5.6-terra` whatever model is requested. The routing logic is built and tested (−25% simulated on the frozen suite) but ships off by default.
3. **Prompt caching can't be forced.** It is automatic on the proxy (~10× cheaper per cached token) but unreliable run to run, which also swings the dollar rows above.
4. **The refusal-reason rule only half works.** Telling the model to name the tool's refusal reason improved golden facts (0.84 → 0.98), but the shipped / past-window refusals still drop the reason in about half the runs.

## 6. What we would watch in production

| Metric | Threshold | Who gets paged |
|---|---|---|
| Golden-set score (nightly eval) | < 0.90 | on-call eng — quality regression |
| Guardrail refusal cases (nightly) | any case changes an order it shouldn't | on-call eng — safety |
| Tool error rate (`/logs`) | > 15% | on-call eng |
| Cost per turn | > $0.02 | eng + finance |
| Turn p95 latency | > 12,000 ms | on-call eng |
| `degraded` events (model timeout / gateway) | > 2% of turns | on-call eng |

The cost, error-rate and p95 alerts are `ALERT_*` thresholds in `config.py`; `observe.check_alerts` fires a distinct `alert` event on breach, surfaced on `/logs`. They are disabled by default; set the thresholds to arm them. `/logs.json` was checked on 2026-10-08: no null fields in stats or in turn / llm / tool / cache events. Caveat: `/logs` reads a trace file the eval runs also write to, so its cost-per-turn mixes eval calls with web turns.

---

## Still open — needs a human

- **Witnessed sign-off (readout rule 3).** The pair watches the after-run and signs here. To reproduce, from `bhargava-code/`: `../tools/phase4_runs.sh` (2 warm-up cases, then `evals.py --budget 200000` and `golden.py --budget 400000`; ~220k tokens, ~10 min).
  - Witness: ____________________  Date: __________  Numbers matched: ☐
- ~~**Failure screenshots** (before/after) of the injection case in the chat UI.~~ Done 2026-10-08: typed into the real chat UI with headless Chrome (`../tools/screenshot_chat.py`). Before (`cd098e0`, IPv4 shim so the network is not the cause): no reply after 90 s, still "thinking…" — the old retry loop. After (`20f433d`): "I'm having trouble completing that right now. Let me get a human agent to take a look" in 14.2 s, no tools called. Images in `docs/evidence/`.
- **S5 — trustworthy to users (3-person study).** Prepared in `docs/USER_STUDY.md`, not run.
- **Local network note:** on a network that black-holes IPv6 to the proxy, set `LLM_FORCE_IPV4=1` in `.env` (otherwise each new connection waits ~150 s).

## How to reproduce every number here

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest              # 332 passed
python3 evals.py --budget 200000 --out results/evals_final.json
python3 golden.py --budget 400000 --out results/golden_final.json
python3 golden.py --audit                           # judge audit
```
Result files: `results/evals_final.json`, `results/golden_final.json`, `results/evals_phase2a.json` (the 20/20 run), `results/evals_phase2b.json` (the reverted change), `results/baseline_react.json` (before). The before-golden run is `golden_before_cd098e0.json`, produced from a worktree at `cd098e0` with a harness-only fix (its spy recorded no evidence for direct tool calls).
