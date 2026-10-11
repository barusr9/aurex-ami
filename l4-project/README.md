# Ami — L4 project: hardening a support agent, measured

A self-contained copy of the L4 team project on **Ami**, a customer-support agent for a pretend
online store (ReAct + plan-and-execute, policy guardrails, RAG over policy documents, an eval
harness with an LLM judge). The upstream repo is [barusr9/aurex-ami](https://github.com/barusr9/aurex-ami);
this work is open there as [PR #2](https://github.com/barusr9/aurex-ami/pull/2).

This repo exists so the plan, the measurements, the helper scripts and a snapshot of the code can be
used from anywhere, without access to the upstream repo. It contains **no API keys and no personal
data**: configuration comes from `.env` files that are never committed (see `code/.env.example`).

## Result (before → after, same frozen suites, same judge)

| | before (`cd098e0`) | after (`858e9aa`) |
|---|---|---|
| Golden-set score (28 cases) | 0.805 · 16/28 clean | **0.967 · 24/28 clean** |
| Golden agent cost | $0.224 | **$0.139 (−38%)** |
| Behavioural suite (20 cases) | 15/20 | **17–20/20** |
| Behavioural cost per case / p95 latency | 0.89¢ / 17.9 s | **0.79¢ / 13.8 s** |
| Repeated general questions | — | **−54% tokens** (answer cache) |
| Unit tests | 251 passing, 46 failing | **346 passing** (master `317632a`) |

The S1 target "under half the cost" was **not** met (−38% golden, −11% behavioural). The one change that
cut cost further (a 12-word cap on the ReAct thought) broke a guardrail and was reverted. Both are
reported in `code/READOUT.md`.

## Layout

| Path | What it is |
|---|---|
| `code/` | Snapshot of upstream `master` at `317632a`, after PR #2 was merged on 2026-10-08. Run it from here, or clone [barusr9/aurex-ami](https://github.com/barusr9/aurex-ami). |
| `code/READOUT.md` | The one-page readout: goal, before/after, what did not work, what is still open. |
| `code/docs/USER_STUDY.md` | The S5 user-trust study kit (3 participants, 6 tasks, redesign, re-test). |
| `docs/Shree-plan-10072026.md` / `.pdf` | The fix plan, with the execution log of every phase: commands, real output, numbers, decisions, and the pending-items table (§13). |
| `docs/Shree-session-log.md` | Day-by-day record of what was asked, found and done. |
| `docs/PR-description-10082026.md` | The text of PR #2. |
| `docs/S5-facilitator-sheet.md` / `.pdf` | Printable sheet for running the S5 study. |
| `docs/Ami-L4-Readout-Bhargava-Shree-2026-10-08.pptx` / `.pdf` | **The readout deck** (10 slides, speaker notes in the PPTX). |
| `docs/PRESENTATION.md` | Run-of-show for the 5-minute walkthrough: timing, who says what, likely questions. |
| `tools/` | Helper scripts used outside the repo (see below). |
| `evidence/` | Screenshots of the `/logs` dashboard from the live app (populated KPIs, guardrail refusals, a cache hit). |
| `runs/` | Raw logs of the measured runs (golden before/after, evals per phase, cache benchmark, final run). |

## Running the code

```bash
cd code
python3.13 -m venv .venv && source .venv/bin/activate     # 3.13: pandas does not build on 3.14 yet
pip install -r requirements.txt
cp .env.example .env            # the placeholder key in it is enough for the tests; put your real
                                #   OPENAI_API_KEY / OPENAI_BASE_URL / MODEL in .env to run the app or evals
python -m pytest -q             # 346 tests, no network needed (checked on master's tree, 2026-10-08)
PORT=4000 python web.py         # chat UI at http://localhost:4000, dashboard at /logs
python evals.py                 # behavioural suite (uses the model)
python golden.py                # golden set with the LLM judge (uses the model)
```

The web app ships with demo accounts (`demo1@cofy.ai` … `demo5@cofy.ai`, password `demo123`) and a
pretend order database in `ami/store.py`. These are classroom fixtures, not real credentials.
`LLM_FORCE_IPV4=1` in `.env` works around networks that black-hole IPv6 to the proxy.

## Tools

| Script | Purpose |
|---|---|
| `tools/phase4_runs.sh` | The witnessed final measurement: warm-up, behavioural suite, golden set. ~220k tokens. |
| `tools/s5_reset.sh P1` | Restart Ami on port 4000 with fresh orders and no saved chats before each study participant. |
| `tools/screenshot_logs.py` | Capture `/logs` from the running app with headless Chrome. |
| `tools/web_logs_check.py` | Check `/logs.json` for null values and exercise the answer cache. |
| `tools/cache_benchmark.py` | Repeated-question benchmark for the answer cache. |
| `tools/eval_summary.py`, `tools/dryrun_eval.py` | Summarise an eval result; dry-run the harness offline. |
| `tools/phase1_execlog.sh`, `tools/capture.sh` | Re-run Phase 1 steps and capture command + output into the plan. |
| `tools/md2pdf.py` | Markdown → PDF with headless Chrome (needs `pip install markdown`). |
| `tools/build_deck_pptx.js`, `tools/deck2pdf.py` | Rebuild the readout deck as PPTX (pptxgenjs) and print the slide HTML to PDF (headless Chrome). |
| `tools/ipv4_sitecustomize.py` | Optional: force IPv4 for a whole Python process via `PYTHONPATH`. |

## Status

Done: Phases 0–4 (fixes, cost work, golden score, final measurement, readout); **PR #2 reviewed by Bhargava and merged into master on 2026-10-08** (`317632a`).
Open: S5 study sessions and redesign, witnessed re-run and sign-off (follow-ups go in a new PR). The live
pending list is §13 of `docs/Shree-plan-10072026.md`.
