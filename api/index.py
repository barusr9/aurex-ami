"""Vercel entry point: the same Handler web.py runs locally, served as a function.

Vercel's Python runtime looks for a class named `handler` that subclasses
BaseHTTPRequestHandler and routes every request to it (see vercel.json). The
app keeps its generated files under STATE_DIR / CACHE_DIR, which the project
settings point at /tmp because a function's filesystem is read-only and not
shared between instances. Consequences, stated plainly:

  - sessions, the trace, escalation tickets and feedback live only as long as
    the instance does; use the escalation webhook / email / Jira backend so a
    hand-off reaches a human somewhere durable
  - the first request on a cold instance downloads the 17 MB embedding model
    and rebuilds the knowledge index into /tmp, which can take 10-20 s
  - a turn can run up to the LLM timeout (60 s); vercel.json raises the
    function's maxDuration to match

For a long-lived process with a disk, the Dockerfile next to this file is the
better deployment. This adapter exists so the GitHub repo deploys on Vercel
with no code changes.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("STATE_DIR", "/tmp/ami/state")
os.environ.setdefault("CACHE_DIR", "/tmp/ami/cache")

from web import Handler as handler  # noqa: E402  (import after the path and env are set)
