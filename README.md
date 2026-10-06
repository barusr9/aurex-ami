# Ami — Amazon Customer Support Agent

A self-contained support chatbot. Four parts: a **profile** (who the agent is),
**memory** (what it remembers about a customer), **planning** (what step to take
next), and **action** (tools + guardrails). Served from a single Python file over
a plain HTTP server — no web framework.

## Requirements

- Python 3.10+
- An OpenAI-compatible API key

## Setup

```bash
# 1. (optional) create a virtualenv
python3 -m venv .venv && source .venv/bin/activate

# 2. install dependencies
pip install -r requirements.txt

# 3. configure secrets
cp .env.example .env
# then edit .env and set OPENAI_API_KEY (and OPENAI_BASE_URL / MODEL if needed)
```

## Run

```bash
python3 web.py                 # defaults to http://localhost:9001
PORT=4000 python3 web.py       # or pick a port
```

Open the URL and sign in with a demo account:

| Email            | Password  |
|------------------|-----------|
| `demo1@cofy.ai`  | `demo123` |
| `demo2@cofy.ai`  | `demo123` |
| ... through `demo5@cofy.ai` | `demo123` |

## What's inside

```
web.py            the HTTP server and all routes (chat UI, login, /logs)
main.py           run the agent from the terminal
ami/              the agent package
  agent_profile.py   the profile: who Ami is
  memory.py          working + long-term memory
  planner.py         ReAct planner  |  plan_execute.py  plan-and-execute
  tools.py           the actions (find orders, track package, escalate, ...)
  policy.py          guardrails between the model and the tools
  knowledge.py       retrieval over the written rules in knowledge/
  observe.py         observability: every call, its cost and latency
  dashboard.py       the /logs page
knowledge/        the written support policies, retrieved at answer time
ui/               the HTML pages (login, chat, logs)
evals.py          scored evals against golden.json
golden.json       the test cases
tests/            unit tests
```

## Observability

Sign in, then open **`/logs`** (e.g. http://localhost:9001/logs) for a live
dashboard of model calls, tool usage, cost per turn, and latency percentiles.
The raw event stream is written to `state/trace.jsonl`.

## Evals

```bash
python3 evals.py               # score every golden case once
python3 evals.py --runs 3      # three runs each (they are not deterministic)
```

## Notes

- `.env` holds your real key and is **git-ignored** — never commit it.
- `state/` and `results/` are generated at runtime and start empty.
