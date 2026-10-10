# Order prefetch: A/B on the frozen suite, 2026-10-10

Same code (master f09367e), same proxy, same hour, 33 frozen cases (20 behavioural + 13 complaint). Only the env flag changed.

| Run | Pass | Model calls (20 behav.) | Input tokens | Cached tokens | Median turn | p95 | Cost, 33 cases |
|---|---|---|---|---|---|---|---|
| PREFETCH_ORDERS=0 | 17/20, 12/13 | 54 | 108k | 71% | 4.7 s | 9.6 s | $0.162 |
| PREFETCH_ORDERS=1 (default) | 17/20, 13/13 | 50 | 97k | 45% | 3.9 s | 9.6 s | $0.206 |
| =1 + brief moved after the history (experiment, reverted) | 18/20, 13/13 | 56 | 109k | 28% | 5.0 s | 10.8 s | $0.248 |

Files: results/evals_prefetch_off_2026-10-10.json, results/evals_prefetch_on_2026-10-10.json, results/evals_prefetch_on_brief_end_2026-10-10.json. Cached-token shares from state/trace.jsonl llm events in each run's time window.

## Reading

- Prefetch does what it was built for: 4 fewer model calls, 10% fewer input tokens, median turn 17% faster, same pass rate. Example: "status by order id" goes from 2 calls / 0.38¢ to 1 call / 0.28¢.
- It does not save dollars on this proxy. The proxy's prompt cache hit 71% of input tokens with prefetch off and 45% with it on, so fewer tokens were billed at a higher average rate. Moving the working-memory brief to the end of the prompt, to keep the system prompt a stable prefix, made the cache worse (28%), so the cache is not simply prefix-driven from our side.
- Across three runs within ten minutes the cache share ranged 28% to 71%. This is the "prompt caching is unpredictable" finding from the readout, measured again. Dollar cost on this proxy cannot be driven down from inside the agent until caching is consistent.

## Decision

Prefetch stays on by default (fewer calls, faster turns, same quality). No cost saving is claimed for it. The brief-at-end change was reverted and is not in master.
