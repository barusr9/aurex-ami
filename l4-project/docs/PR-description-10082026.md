## Harden Ami: confirmation flow, cost (S1), reliability, final readout

Builds on #1 and on master `1b04d45` (merged in, conflicts resolved). Branch: `fix/s1-and-eval-failures`.

### Before → after (same frozen suites; measured before the merge with master — re-run witnessed)

| | before (`cd098e0`) | after (`858e9aa`) |
|---|---|---|
| **Golden score** (28 cases) | 0.805 · 16/28 clean | **0.967 · 24/28 clean** |
| Golden agent cost | $0.224 | **$0.139 (−38%)** |
| **Behavioural** (20 cases) | 15/20 | **17/20** (20/20 in a 2nd run of the same code) |
| Behavioural cost per case / p95 | 0.89¢ / 17.9 s | **0.79¢ / 13.8 s** |
| Complaint cases (10) | — | **10/10** |
| Repeated general questions | — | **−54% tokens** (answer cache) |
| Unit tests | 251 / 46 failing | **342 passed** (after merge) |

S1's "under half the cost" target was **not** met on the frozen suites (−38% golden, −11% behavioural) — reported in READOUT §3.

### What changed
- **Confirmation flow actually works.** ReAct called `tools.run` directly, bypassing `policy.guarded_run`, and cancel/return schemas had no `confirmed` — a cancel or return could never complete. Every tool call now goes through the policy layer, which passes the user's scope and hands `confirmed=True` to the tool only after a "yes" in a later turn.
- **Eligibility before confirmation.** Shipped / past-window / not-yours orders are refused immediately, never "please confirm".
- **Fail fast.** SDK hidden retries off; separate retry budgets for rate limits (75 s) and gateway errors (15 s); a **total** per-call time limit (the SDK timeout is per read — a stalled connection hung a turn 15+ min). React returns the graceful `DEGRADED_REPLY` on model failure. The injection case went from a 14-min hang + crash to a graceful reply.
- **Policy notes and long-term context reach the model.** `web.py` now scrubs card numbers *before* the text enters memory (it reached the model before), and uses the same system prompt (with planning rules) the evals measure.
- **Compact prompt (−37% fixed prefix).** Same rules, duplicates merged; two rules from the golden failures (name the refusal reason; answer policy questions first); the "look up tone before refusing" extra call removed.
- **Answer cache** (`ami/answer_cache.py`): only a conversation's first, PUBLIC message answered from the knowledge base alone; keyed by text + a knowledge-doc stamp; TTL, LRU; failure replies never cached.
- **Harness:** find-by-email cases log in as the customer they name; with prefetch merged, direct tool calls outside the guard are counted in `called` and given to the judge as evidence.
- **Config:** `.env` is loaded before `config.py` reads it (values set only in `.env` were ignored); opt-in `LLM_FORCE_IPV4=1` for networks that black-hole IPv6 (each connection waited ~150 s).

### What did NOT work (READOUT §5)
Capping the ReAct thought at 12 words cut output cost 13% but dropped the behavioural suite 20/20 → 16/20 (`guard: authority claim` called `start_return`). Reverted (`d07e8d3` → `81b0cf5`).

### Merge with master (`20f433d`)
- `planner.py`: kept both the context block and Bhargava's prefetch.
- `evals.py`: guard spy is the complete record; prefetch's direct `tools.run` is added to `called`/`observed`.
- Offline dry-runs: cancel flow completes; prefetched `get_order` is counted and passed to the judge.

### Still open
- [ ] Witnessed run on the merged branch: `../tools/phase4_runs.sh` (~220k tokens) → replace READOUT numbers, sign.
- [ ] Failure screenshots (chat UI). `/logs` evidence screenshot captured (no nulls; cache hit 1 ms / $0).
- [ ] S5 three-person study (`docs/USER_STUDY.md`).
- [ ] Known: refusals sometimes drop the reason ("shipped", "30-day"); `/logs` cost-per-turn mixes eval calls into web turns.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
