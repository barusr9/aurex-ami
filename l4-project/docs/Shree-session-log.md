# Session Log — Shree × Claude (Ami / aurex-ami L4 project)

A running record of what was asked, found, decided and done in the working session with Claude Code. The detailed plan, with commands and outputs, lives in `Shree-plan-10072026.md` / `.pdf`.

**Workspace:** `~/Desktop/AI-Modern-L4-training-pt09252026/Project-Shree-Bhargava/`

| Path | What it is |
|---|---|
| `bhargava-code/` | Clone of https://github.com/barusr9/aurex-ami (working repo) |
| `bhargava-before/` | Git worktree at baseline commit `cd098e0` (for "before" measurements) |
| `Shree-plan-10072026.md` / `.pdf` | Fix plan + progress log + execution log |
| `Shree-session-log.md` | This file |
| `tools/` | Helper scripts: `capture.sh`, `phase1_execlog.sh`, `dryrun_eval.py` (outside the repo) |
| `runs/` | Raw logs of API runs (golden, evals) |
| `*.txt`, `*.png` | Meeting notes, Balaji's email, Bhargava's messages/screenshots |

---

## 2026-10-06 — Setup and first analysis

1. **Created the project folder.** First as `Project-Shree-Bharagava` (typo as given), then renamed to `Project-Shree-Bhargava`.
2. **Cloned the repo** into `bhargava-code/`.
3. **Analysed the 10/05 meeting + Balaji's email.** The assignment: pick ONE of six upgrades, measure before/after, fill the one-page readout and present it together. The team leaned towards #6 (model routing).
4. **Code review of the original repo.** The design is solid, but the eval harness crashed on every case (`react()` signature drift); plan-and-execute had a missing `notes()`; cancel/return could never complete; 46 of 297 unit tests were failing.
5. **Environment:** created `bhargava-code/.venv` with **Python 3.13** (miniconda) — pandas won't build on the default Python 3.14.
6. **API key, first attempt:** the `AI-Architect_L2_Aug_2026` key had expired ("practice window has ended"). The L4 folder's key worked, but **the proxy serves `gpt-5.6-terra` whatever model is requested**, so live model routing (#6) can't show savings on this proxy.

## 2026-10-07 — Bhargava's update and Phase 1

7. **New inputs:** the 10/06 meeting notes, a new repo note, and a WhatsApp screenshot.
   - Bhargava merged PR #1 (S1–S6 work) to master `ae77fb4`.
   - Bhargava's token budget is exhausted; asked Shree to "fix the rest".
   - Status: S2/S3/S4/S6 done · **S1 in progress (budget-blocked)** · **S5 needs 3 people**.
8. **Pulled the latest master** and analysed READOUT.md, brd.md and sdr.md.
   - The readout shows the score flat at 15/20, cost not under half, golden-set score never run, and the witness/S5 still open.
9. **Root causes found:**
   - The same 5 eval cases failed in both before and after runs: the confirmation flow bypassed (cancel/return never complete); confirmation asked before eligibility; scope dropped in `guarded_run`; a proxy 502 retried for about 14 min; the eval logged in as the wrong user.
   - Also: policy notes never reached the model in the ReAct path.
10. **Key check:** the L4 key had been rotated (401). Couldn't confirm the 502-on-injection hypothesis.
11. **Plan agreed** (Phases 0–6) and written to `Shree-plan-10072026.md/.pdf`.
12. **Phase 1 done** on branch `fix/s1-and-eval-failures`, commit **`f56b651`** (local, not pushed). 0 tokens used.
    - Confirmation flow through the policy layer; eligibility before confirmation; fail-fast retries plus a degraded reply; notes and long-term context reach the model; eval login fix.
    - **Extra bugs fixed:** web stored card numbers before scrubbing them; web ran without the planning rules; `notes()` was missing; `WorkingMemory.record` crashed on previews.
    - Tests: **312 → 324 passed, 0 failed**.
13. **Execution log:** every Phase 1 step was re-run and its command and real output captured into the plan PDF (section 7, 20 blocks, all exit 0). Reusable via `tools/phase1_execlog.sh`.

## 2026-10-08 — New key and Phase 3

14. **New API key** saved by Shree in `bhargava-code/.env` (`mai_05…`, `MODEL=gpt-5.6-terra`). Tested: it works.
    - The first call took **121 s** (cold start); the next took 1.4 s.
    - Decision: a warm-up call before every measured run.
15. **Shree asked to go ahead with Phase 3 (golden-set score)** before Phase 2.
    - Checked: `golden.json` unchanged since 2026-10-06 (frozen ✅); the judge rubric is identical at `cd098e0` and HEAD.
    - Created worktree `bhargava-before/` at `cd098e0` for the "before" run.
    - Run order (one at a time, under the proxy's 60 req/min): warm-up → judge audit → golden **after** (Phase 1 code) → golden **before** (`cd098e0`).
    - Note: golden "after" must be re-run once Phase 2 changes land.

---

## Open items (owner)

- Tell Bhargava Shree is editing `planner.py`, `policy.py`, `tools.py`, `llm.py`, `web.py`, `evals.py` *(Shree)*
- Push branch / open PR — waiting for Shree's go-ahead *(Shree)*
- Phase 2 (S1 cost/caching), Phase 4 (witnessed run + READOUT), Phase 5 (S5 study), Phase 6 (merge before the 11th)

## Phase 3 results
*(filled in below as runs complete)*

### Step 3.0 — Warm-up + judge audit ✅ (2026-10-08)
| Check | Result |
|---|---|
| Warm-up call | **152.3 s** (cold start again), served by `gpt-5.6-terra-2026-07-09` |
| Judge audit (`golden.py --audit`) | **28/28 rows told apart**; own references 0.98 (want 1.00); unrelated references 0.05 (want low) |
| Only weak row | `tone-upset-customer`: its own reference scored 0.5 ("acknowledgment is instructed, not actually given"). The reference itself is borderline; treat that row's judged score with caution |
| Judge cost / time | $0.102 · 3 min 43 s |

Verdict: **the judge can be trusted** for the golden runs.
Side finding: the run header prints `gpt-4o-mini` because `config.py` reads `MODEL` before `.env` is loaded. Only the label is wrong — the proxy serves `gpt-5.6-terra` and cost is priced from the served model.

### Network fix ✅ (commit `652c630`)
The ~150 s first call was **IPv6 black-holed on this network** (two IPv6 connect timeouts before IPv4). Proven with socket/curl/httpx tests. Added opt-in `LLM_FORCE_IPV4=1` (only in Shree's `.env`) → first call **1.3 s**. Also fixed `config.py` loading `.env` too late. Tests 324 passed.

### Step 3.1 — Golden AFTER (Phase 1 code) ✅
**16/28 clean (57%) · avg score 0.856 · agent $0.257 + judge $0.069 · p50 3,804 ms · p95 12,381 ms · 154k tokens.**
Failures: 1 harness (ord-by-email login) · 2 refusal reason not stated · 2 asked for an order number instead of quoting policy · 7 partial answers. Grounded 0.98 — omissions, not hallucinations. Details in the plan PDF §8.

### Step 3.2 — Golden BEFORE (`cd098e0`) ✅
- First attempt **aborted after 6 rows**: the old harness gave the judge no evidence (old react bypassed the spy), so grounded/retrieval read 0. That saved ~130k tokens.
- Fixed the **harness only** in the worktree (`spy_run` records direct tool calls); verified offline; re-ran.
- Result: **16/28 clean · score 0.805 · $0.224 · p50 4,738 ms · p95 13,010 ms**.

### Phase 3 RESULT ✅ — before vs after (same 28 frozen rows, same judge)
**Score 0.805 → 0.856 (+0.05)** · retrieval +0.07 · correct +0.07 · grounded 0.93 → 0.98 · p50 −20% · p95 −5% · rows clean flat 16 → 16 · **cost +14% (worse — report it)**.
Clear win: `ord-cancel` 0.33 → 1.00 (the confirmation fix). Clear regression: `grd-cancel-shipped` (reply drops "shipped"), which a Phase 2 prompt rule targets.
**Phase 3 tokens:** audit ~$0.10 · after-run 154k agent tokens · before-run (no token count in the old harness) $0.299.

## Phase 2 — S1 cheaper and faster (2026-10-08)
- **2.0** Harness: log in as the customer whose email the turn names (commit `6c31bd8`). Fixes evals "find by email" + golden "ord-by-email".
- **Token analysis:** ~99% of each call is the fixed prefix (prompt + schemas ≈ 2,061 tok). Levers = smaller prefix + fewer calls. Transcript trimming dropped (wouldn't help this suite).
- **2.1** Evals on Phase 1 code: frozen 20 **15 → 18/20**, cost/case 0.89¢ → 0.82¢; complaints 10/10. p95 75 s caused by the injection case's 75 s retry wait (the proxy 502s that text every run) — it now passes gracefully.
- **2A** (commit `0876ef7`): compact prompt (prefix −37%), refusal-reason + policy-first rules, tone lookup removed, 15 s gateway retry budget. Measuring…
- **2A result:** frozen 20 **20/20** · tokens **132.8k → 79.5k (−40%)** · calls 69 → 59 · p95 75 s → **13.2 s** · complaints 9/10 (a matcher false positive: the reply correctly says "can't be … refunded without a return"). Dollars ~flat because the new prefix started with a cold cache (hits 79% → 48%); output is ~40% of cost ($12/M).
- **2B** (commit `d07e8d3`): cap the ReAct `thought` at 12 words to cut output tokens. Measuring…
- **2B result ❌ reverted:** the 12-word thought cap saved 13% output $ but frozen fell **20 → 16/20** (authority-claim guardrail broke). Commit `d07e8d3`, reverted in `81b0cf5`. This is the readout's §5 "what did NOT work".
- **Reliability fix (`fbe2af9`):** the first cache benchmark hung 15+ min in an SSL read (the SDK timeout is per read, not per call). Added a total per-call time limit (60 s), one retry, then a graceful reply. 332 tests pass.
- **2C answer cache (`858e9aa`) ✅:** benchmark of 5 general questions × 3 asks → **8/10 repeat hits**, tokens **39.8k → 18.6k (−54%)**, $ −53%, a hit takes 1–2 ms with 0 model calls. One question ("refunds" wording) is classified PRIVATE and never cached, by design.
- **Phase 2 done.** Kept: harness login, 2A, the timeout fix, 2C. Reverted: 2B. Next: Phase 4 witnessed final run (warm cache) + golden re-run on the Phase 2 prompt.

## Phase 4 — final measurement + READOUT (2026-10-08)
- **Final runs** (`tools/phase4_runs.sh`, commit `858e9aa`): behavioural **17/20** (20/20 in run 2A on the same code → variance, report 17–20) · cost/case 0.79¢ (−11%) · p95 13.8 s (−23%) · complaints 10/10. **Golden 24/28, score 0.967 (was 0.805), agent cost $0.139 (−38%)**.
- **/logs check (item F):** no null values in stats or events; the answer cache works in the real web app (new session, 0.00 s). Caveat: `/logs` mixes eval calls into cost-per-turn.
- **READOUT.md** rewritten with final numbers, honest S1 miss (not under half), §5 negatives (commit `a8c1f3a`; 7 result files committed).
- **Open (needs people):** witness sign-off (Bhargava watches `tools/phase4_runs.sh`), failure screenshots, S5 3-person study, push + PR.
- **Tokens used in Phase 4:** ~225k (final evals 112k + golden 106k + warm-up 4k + web check ~5k).
- **Evidence screenshot (4.4):** `/logs` dashboard captured from the live web app with headless Chrome (`tools/screenshot_logs.py`): `evidence/logs-dashboard-top-10082026.png` (top: KPIs, tool usage, newest events) and `evidence/logs-dashboard-10082026.png` (full page). Shows populated KPIs (no nulls), guardrail refusals, and a cache hit (1 ms, $0) next to the same question's first ask (3,895 ms, $0.00259). Embedded in the plan PDF §10.

## Push / PR (2026-10-08)
- Decision: **separate branch** `fix/s1-and-eval-failures`, PR into `barusr9/aurex-ami:master` (same pattern as PR #1).
- Shree's account has **read-only** access to `barusr9/aurex-ami`; a fork exists at `shreenathacc22/aurex-ami`.
- Bhargava pushed 6 new commits to master today (harness `observed` fix, golden 16/28, evals `--exclude`, S1 order **prefetch**, S2 alerts armed, Goal 3 cases). **Merged master into our branch** (`20f433d`), resolved planner.py / evals.py / .env.example / .gitignore, **342 tests pass**, offline dry-runs OK. READOUT notes that its numbers predate the merge.
- Secret scan before push: `.env` not tracked, no keys in tracked files.
- **Push to the fork was blocked** by Claude Code's permission check (adding a remote = "remote repoint"). Shree runs the push/PR commands; the PR description is in `PR-description-10082026.md`.

## Push / PR done (2026-10-08, new terminal session)
- Re-checked: working tree clean, no `.env` or keys tracked.
- Pushed `fix/s1-and-eval-failures` (`20f433d`) to the fork: https://github.com/shreenathacc22/aurex-ami/tree/fix/s1-and-eval-failures
- Opened **PR #2** into `barusr9/aurex-ami:master`: https://github.com/barusr9/aurex-ami/pull/2
- Still open: witnessed run + READOUT sign-off (Bhargava), failure screenshots, S5 study, merge before the 11th.

## Phase 5 — S5 study prep (2026-10-08)
- Found: only demo1 has orders, so demo2/demo3 would hit "no orders" on tasks 1–4. Fix: everyone uses demo1, with an app reset between participants (`tools/s5_reset.sh P#`; orders and memory are in-memory, and saved sessions are moved aside).
- Smoke test: logins demo1–4 OK; "when did my AirPods arrive?" answered correctly in 7.0 s.
- Facilitator sheet: `S5-facilitator-sheet.md` / `.pdf`. Ami is running on http://localhost:4000, reset and ready for P1.
- PDF builder copied to `tools/md2pdf.py`, with its own env in `tools/.pdfenv`.
- Pending list now lives in plan §13 and is updated after every phase.

## Public repo + failure screenshots (2026-10-08)
- Public copy created at https://github.com/shreenathacc22/ami-l4-project (plan + PDF, logs, tools, evidence, runs, code snapshot of `20f433d`). Scanned: no API key value, no `.env`, no personal messages (meeting notes, Balaji's email and screenshots were left out on purpose). Plan §14.
- READOUT open item "failure screenshots" done: injection case typed into the real chat UI with headless Chrome (`tools/screenshot_chat.py`). Before: still "thinking…" at 90 s. After: handoff reply in 14.2 s, no tools called. Added to the PR branch (`docs/evidence/`, commit `851a707`) and pushed, so PR #2 is updated. Plan §15.
- Pending list (§13): item 5 closed; items 1–4, 6, 7 remain.

## Deck + public repo check (2026-10-08)
- Deck built as a Slides artifact (10 slides, notes with timing): https://claude.ai/artifact/KMns74rheLukvPD6BzQzoW — private until shared. Plan §16.
- Fresh clone of https://github.com/shreenathacc22/ami-l4-project: 342 tests pass with the placeholder key from `.env.example`; README made explicit about it.

## Item 6 prepared (2026-10-08)
- Deck exported as `Ami-L4-Readout-Bhargava-Shree-2026-10-08.pptx` (pptxgenjs, validated) and `.pdf` (Chrome print of the live deck). Run-of-show in `ami-l4-project/docs/PRESENTATION.md`. Both files in this folder and in the public repo. Plan §17; pending item 7 now "delivery only".

## PR #2 merged (2026-10-08)
- Verified on GitHub: PR #2 state MERGED at 18:50 UTC, 11 commits, no review comments; `851a707` is an ancestor of `origin/master` (`317632a`). Local master fast-forwarded; public repo snapshot updated to master. Plan §18. Pending: items 1–4 (S5, witnessed run) → new PR; item 6 delivery of the readout.
- Correction: Bhargava's review was done as commits after the merge — a security fix to our Phase 1 `guarded_run` (model-supplied `scope` was consulted before the session's; now dropped unconditionally, with a new test) and a test-flake fix. Master runs 346 tests green. To be added to the READOUT's §5 in the follow-up PR.

## 2026-10-09 — Bhargava call, meeting notes, deck v2
- Recording analysed from `10092026-zoom-recording/` (80 min; Shree, Bhargava, Kumar). Transcribed locally with faster-whisper (nothing uploaded); transcript saved beside the recording; keyframes used for screen context.
- Meeting document (summary, discussion points with timestamps, decisions, Bhargava's slide-by-slide notes, action items with owner/due/status, metric glossary, sources): https://claude.ai/code/artifact/834f528b-e282-41b0-8305-4f5d8c6e4505
- Bhargava's structure applied to the deck: product (login gate before/after) → the ask (six goals) → what we found → **one results table by goal with Met/Partial verdicts** → what we changed by goal and layer → where this goes next; measurement, "what did not work" detail and the watch list moved to appendix A1–A4. 7 presented slides, 4:50. Bhargava slides 1–3, Shree 4–7.
- Live deck republished (v19), PPTX rebuilt and validated, PDF reprinted (11 pages) and checked page by page; run-of-show rewritten. Plan §19.
- Side effect fixed: stopping the stage2 server also stopped the Ami app on 4000; restarted with `tools/s5_reset.sh P1`.
- Next: rehearsal Fri 10 Oct 2–3 pm; send Kumar the links; S5 sessions and witnessed run still open (plan §13).
- Second PPTX built on request: the 8 October slides in the listed order (injection second), `Ami-L4-Readout-Bhargava-Shree-2026-10-08-original-flow.pptx`, validated; plan §20. Deck v2 unchanged.
