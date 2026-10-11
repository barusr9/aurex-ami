# Policy prefetch (goal 3): A/B on the three written-policy cases, 2026-10-11

Same code (branch `goal3-policy-prefetch` at 9019c86 = master 1110f38 + `prefetch_policy`), same proxy, same minute, 3 cases x 2 runs each. Only the env flag changed. Escalations backend forced to `none` by evals.py, so no tickets were sent.

| Run | Pass | Model calls (6 turns) | Cost / turn | Median turn | Tokens |
|---|---|---|---|---|---|
| PREFETCH_POLICY=0 (control) | 6/6 | 16 | 0.95¢ | 4.9 s | 25,642 |
| PREFETCH_POLICY=1 (default) | 6/6 | 9 | 0.55¢ | 2.1 s | 13,560 |

Files: results/goal3_before_same_code.json, results/goal3_after.json.

## Reading

- The two delivery cases ("missing package", "stalled tracking") drop from 2 model calls to 1: the written policy is in working memory before the first call, so the model answers from it instead of asking for `search_knowledge` first.
- The address-change case still needs `get_order` and `escalate`; it drops from 4 calls to 2-3.
- `search_knowledge` is called on every turn in both arms. On master without prefetch it was skipped on the address-change case in 2 of 3 earlier runs (8 and 10 Oct), which is the failure this change was built to remove. In this sample of 2 the control also passed, so the pass-rate claim rests on the earlier runs, not on this one.
- Unlike order prefetch, this one also saved dollars here (-42% per turn); the proxy's cache was kind in this minute. Treat the cost figure as one run, the call count and latency as structural.

## Decision

Prefetch of the written policy stays on by default on this branch. Ready to merge into master; 420 unit tests pass on the merged tree.
