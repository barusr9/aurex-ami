# Ami — Amazon Customer Support Agent

A self-contained support chatbot. Four parts: a **profile** (who the agent is),
**memory** (what it remembers about a customer), **planning** (what step to take
next), and **action** (tools + guardrails). Served from a single Python file over
a plain HTTP server — no web framework.

## Quick start

```bash
# 1. clone
git clone https://github.com/barusr9/aurex-ami.git
cd aurex-ami

# 2. (recommended) create a virtualenv
python3 -m venv .venv && source .venv/bin/activate

# 3. install dependencies
pip install -r requirements.txt

# 4. add your API key
cp .env.example .env
#    then open .env and set OPENAI_API_KEY (and OPENAI_BASE_URL / MODEL if needed)

# 5. run
python3 web.py
```

Then open **http://localhost:9001** and sign in with a demo account below.

## Requirements

- Python 3.10+
- An OpenAI-compatible API key (set in `.env`)

## Configuration

Copy `.env.example` to `.env` and fill it in. Only the first line is required:

| Variable          | Required | Default                     | Purpose                          |
|-------------------|----------|-----------------------------|----------------------------------|
| `OPENAI_API_KEY`  | **yes**  | —                           | your API key                     |
| `OPENAI_BASE_URL` | no       | `https://api.openai.com/v1` | point at a different endpoint     |
| `MODEL`           | no       | `gpt-4o-mini`               | which model to call              |
| `PORT`            | no       | `9001`                      | server port                      |
| `HOST`            | no       | `127.0.0.1`                 | bind address                     |

`.env` is **git-ignored** — your key never gets committed.

## Run

```bash
python3 web.py                 # web UI at http://localhost:9001
PORT=4000 python3 web.py       # or pick a port

python3 main.py                # run the agent in the terminal (ReAct)
python3 main.py --plan         # plan-and-execute planner instead
python3 main.py --baseline     # original loop: no planning, no memory
python3 main.py --quiet        # hide the reasoning trace
```

### Demo login

The web UI requires sign-in. Five seeded demo accounts, all password `demo123`:

| Email                      | Password  |
|----------------------------|-----------|
| `demo1@cofy.ai`            | `demo123` |
| `demo2@cofy.ai` … `demo5@cofy.ai` | `demo123` |

## Observability

Sign in, then open **`/logs`** (e.g. http://localhost:9001/logs) for a live
dashboard of model calls, tool usage, cost per turn, and latency percentiles
(auto-refreshes every 5s). The raw event stream is written to `state/trace.jsonl`.

## Evals

Evals make real model calls, so they need a working API key in `.env` and
cost a few cents per full run. Results land in `results/eval_results.json`
with cost, latency and steps per case.

```bash
python3 evals.py                 # score every case once (ReAct planner)
python3 evals.py --planner plan  # score the plan-and-execute planner
python3 evals.py --runs 3        # three runs each — answers are not deterministic,
                                 # so a case can pass one run and fail the next
python3 evals.py --only guard    # just cases whose name contains "guard"
```

The eval agent runs authenticated as the order's owner (the seed orders
belong to several demo customers); the auth *gate* itself is covered by the
unit tests in `tests/test_isolation.py`.

## Tests

```bash
pip install pytest                                 # test-only dependency
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest            # run the unit tests in tests/
```

> **Why the env var:** if a globally-installed `langsmith` is present, its
> pytest plugin crashes at collection on Python 3.12 (a pydantic/ForwardRef
> incompatibility) before any test runs. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`
> skips third-party plugin autoloading so the suite collects. Plain `pytest`
> works in environments without that package.

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

## Notes

- `.env` holds your real key and is **git-ignored** — never commit it.
- `state/` and `results/` are generated at runtime and start empty.
- First run downloads a local embedding model into `.cache/`, so it may take a
  little longer; subsequent runs are fast.
