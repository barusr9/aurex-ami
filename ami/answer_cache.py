"""Answer cache (S1): the same general question gets the same answer, free.

A support queue repeats itself — "what's your return policy?" arrives all
day — and every repeat used to cost a full ReAct turn (two model calls with
the whole prefix). The answer depends only on the written rules, so it can
be reused until those rules change.

What is cached is deliberately narrow, so no account data can leak:

  - the customer's FIRST message in a conversation (no context to depend on)
  - classified PUBLIC (not about their orders or account)
  - answered with no tool other than search_knowledge (nothing about orders
    was looked up, nothing was changed)

The key is the normalised question plus a stamp of the knowledge documents,
so editing a policy invalidates every answer built on the old text. Entries
also expire after a TTL, and the cache is bounded (LRU).
"""

import hashlib
import re
import threading
import time
from collections import OrderedDict

from ami import observe

TTL_SECONDS = 3600
MAX_ENTRIES = 500
CACHEABLE_TOOLS = {"search_knowledge"}

_entries = OrderedDict()          # key -> (stored_at, reply)
_lock = threading.Lock()


def _normalise(text):
    text = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return " ".join(text.split())


def _knowledge_stamp():
    """Changes whenever a knowledge document changes."""
    from ami import knowledge
    h = hashlib.sha256()
    for path in sorted(knowledge.DOCS.glob("*/*.md")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:16]


def key(text):
    return f"{_knowledge_stamp()}:{_normalise(text)}"


def eligible(query_type, first_turn):
    """Can this message be answered from, or stored in, the cache?"""
    return query_type == "PUBLIC" and first_turn


def get(text):
    k = key(text)
    with _lock:
        hit = _entries.get(k)
        if hit and time.time() - hit[0] <= TTL_SECONDS:
            _entries.move_to_end(k)
            observe.log("cache", result="hit")
            return hit[1]
        if hit:
            del _entries[k]               # expired
    observe.log("cache", result="miss")
    return None


def put(text, reply, tools_used):
    """Store the reply only if the turn touched nothing but the knowledge base."""
    if not reply or any(t not in CACHEABLE_TOOLS for t in tools_used):
        return False
    # A failure reply (model down, step limit) uses no tools either, but it
    # must never be served to the next customer as "the answer".
    from ami import planner
    if reply == planner.DEGRADED_REPLY or reply.startswith("I'm not able to sort this out"):
        return False
    k = key(text)
    with _lock:
        _entries[k] = (time.time(), reply)
        _entries.move_to_end(k)
        while len(_entries) > MAX_ENTRIES:
            _entries.popitem(last=False)
    return True


def clear():
    with _lock:
        _entries.clear()


def answer(text, query_type, convo, work, run):
    """One customer turn through the cache.

    run() produces the reply the normal way (the ReAct planner) and returns
    (reply, tools_used). On a hit the transcript still gets the exchange, so
    the conversation can carry on as if the model had answered.
    """
    first_turn = not any(m.get("role") == "user" for m in convo.history[:-1])
    if eligible(query_type, first_turn):
        cached = get(text)
        if cached is not None:
            convo.add_assistant({"role": "assistant", "content": cached})
            return cached, True
    reply, tools_used = run()
    if eligible(query_type, first_turn):
        put(text, reply, tools_used)
    return reply, False
