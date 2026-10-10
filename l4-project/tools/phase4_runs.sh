#!/bin/bash
# Phase 4 final measurement (run from bhargava-code/). Warm the proxy's prompt cache
# with the CURRENT prefix, then the frozen evals, then the golden set.
set -u
echo "=== commit: $(git log --oneline -1)  at $(date '+%Y-%m-%d %H:%M:%S')"
echo "=== warm-up (2 cheap cases, not reported)"
.venv/bin/python -u evals.py --only "out of scope" --out /tmp/warm1.json | tail -1
.venv/bin/python -u evals.py --only "rag: return window" --out /tmp/warm2.json | tail -1
echo "=== FINAL frozen evals"
time .venv/bin/python -u evals.py --budget 200000 --out results/evals_final.json
echo "=== FINAL golden"
time .venv/bin/python -u golden.py --budget 400000 --out results/golden_final.json
echo "=== DONE $(date '+%H:%M:%S')"
