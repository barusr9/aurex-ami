"""The single place where we talk to the model.

Reads OPENAI_API_KEY and OPENAI_BASE_URL from .env. The base URL points at
the class LLM proxy, which speaks the OpenAI chat-completions API.
"""

import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIStatusError

from ami import observe
from ami import pricing
from ami.config import config

load_dotenv()

# Model and retry budget come from config (one source of truth); the env
# vars they read still work exactly as before.
MODEL = config.MODEL


def _prefer_ipv4():
    """Opt-in (LLM_FORCE_IPV4=1): resolve to IPv4 when an IPv4 address exists.

    On a network where IPv6 to the proxy is black-holed, every NEW connection
    spent ~150 s timing out two IPv6 addresses before falling back to IPv4
    (measured: curl -6 cannot connect; IPv4 connects in 0.01 s; a request
    took 151 s by default and 1.2 s with IPv4-only resolution). Binding a
    local IPv4 address did not help — httpx still tried IPv6 — so the fix is
    at name resolution. Hosts with only IPv6 addresses are left untouched.
    """
    original = socket.getaddrinfo

    def ipv4_first(host, *args, **kwargs):
        found = original(host, *args, **kwargs)
        v4 = [a for a in found if a[0] == socket.AF_INET]
        return v4 or found

    socket.getaddrinfo = ipv4_first


if config.LLM_FORCE_IPV4:
    _prefer_ipv4()

# max_retries=0: the SDK otherwise retries 5xx twice on its own, silently,
# INSIDE each of our attempts below — so 6 attempts became 18 requests and
# one bad payload held an eval case for ~14 minutes. Retries live in _call().
_client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ["OPENAI_BASE_URL"],
    timeout=config.LLM_TIMEOUT_SECONDS,
    max_retries=0,
)


RATE_LIMIT_TRIES = config.LLM_RETRY_TRIES


class ModelTimeout(Exception):
    """A model call ran past LLM_TIMEOUT_SECONDS in total."""


# The SDK's timeout is per READ, not per request: a connection the gateway
# accepts but never answers kept a turn blocked in an SSL read for 15+
# minutes (observed 2026-10-08, stack: _ssl__SSLSocket_read -> poll). So the
# call runs on a worker thread and we stop waiting after the total budget.
# A stuck worker finishes or dies on its own; the turn moves on.
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="llm")


def _create(kwargs):
    future = _pool.submit(lambda: _client.chat.completions.create(**kwargs))
    try:
        return future.result(timeout=config.LLM_TIMEOUT_SECONDS)
    except FutureTimeout:
        raise ModelTimeout(f"no response in {config.LLM_TIMEOUT_SECONDS}s") from None

# A gateway hiccup (502/503/504) is the proxy or its origin being briefly
# unreachable, not our request being wrong. Like a 429 it clears on its own,
# so it is a wait, not a failure — otherwise one transient 502 kills a whole
# eval run (observed: a single 502 crashed the suite mid-way).
RETRYABLE_STATUS = {502, 503, 504}


def _call(kwargs):
    """One API call, waiting out the proxy when we ask too fast.

    The class proxy allows 60 requests a minute. That is generous for a
    person typing and nowhere near enough for an eval suite firing turns
    back to back, which is how a 429 first showed up: as fifteen agent
    "failures" that were nothing of the sort. A rate limit is not an error
    to report, it is a queue to join.
    """
    deadline = time.monotonic() + config.LLM_RETRY_MAX_SECONDS
    # A gateway error gets a shorter budget than a rate limit. A real 502
    # blip clears in seconds; one that repeats is usually the gateway
    # rejecting this exact request (the injection eval case gets a 502 every
    # run) and will not clear — waiting 75 s for it only inflated p95.
    gateway_deadline = time.monotonic() + config.LLM_GATEWAY_RETRY_SECONDS
    timed_out = False
    for attempt in range(RATE_LIMIT_TRIES):
        try:
            return _create(kwargs)
        except ModelTimeout as e:
            # One retry on a fresh connection (the stuck one stays busy in
            # its thread); a second stall means the gateway is in trouble.
            if timed_out:
                raise
            timed_out = True
            observe.log("llm", model=kwargs.get("model"), ms=0,
                        error=f"{e}, retrying once")
        except RateLimitError as e:
            # Two different things arrive as a 429, and only one is worth
            # waiting out. "Slow down" clears in under a minute. "This
            # key's budget is used up" never clears, and retrying it buys
            # a minute of silence before the identical failure — which is
            # exactly how a finished eval run looks like a hung one.
            if "insufficient_quota" in str(e) or "budget" in str(e):
                raise
            if attempt == RATE_LIMIT_TRIES - 1:
                raise
            wait = 2 ** (attempt + 1)      # 2, 4, 8, 16, 32 — a minute in all,
                                           # which is the window being enforced
            if time.monotonic() + wait > deadline:
                raise                      # out of retry budget: fail fast
            observe.log("llm", model=kwargs.get("model"), ms=0,
                        error=f"rate limited, waiting {wait}s")
            time.sleep(wait)
        except APIStatusError as e:
            # Only transient gateway errors are worth retrying; a 400/401/404
            # is our mistake and will fail identically on the next try.
            if getattr(e, "status_code", None) not in RETRYABLE_STATUS:
                raise
            if attempt == RATE_LIMIT_TRIES - 1:
                raise
            wait = 2 ** (attempt + 1)
            if time.monotonic() + wait > min(deadline, gateway_deadline):
                raise                      # out of retry budget: fail fast
            observe.log("llm", model=kwargs.get("model"), ms=0,
                        error=f"gateway {e.status_code}, waiting {wait}s")
            time.sleep(wait)


def complete(messages, tools=None, model=MODEL, temperature=0.3):
    """One model call, timed and logged. Everything goes through here."""
    kwargs = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        kwargs["tools"] = tools

    t = observe.timer().__enter__()
    try:
        response = _call(kwargs)
    except Exception as e:
        t.__exit__()
        observe.log("llm", model=model, ms=t.ms, error=f"{type(e).__name__}: {e}")
        raise
    t.__exit__()

    message = response.choices[0].message
    usage = response.usage

    # Input and output are billed at different rates, so record them apart.
    # total_tokens alone cannot be priced.
    tokens_in = getattr(usage, "prompt_tokens", 0) or 0
    tokens_out = getattr(usage, "completion_tokens", 0) or 0
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0

    observe.log("llm",
                model=model,
                ms=t.ms,
                messages=len(messages),
                tokens=getattr(usage, "total_tokens", None),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cached=cached,
                cost=pricing.cost(response.model, tokens_in, tokens_out, cached),
                served_by=response.model,
                finish=response.choices[0].finish_reason,
                tool_calls=len(message.tool_calls or []))
    return response


def chat(messages, model=MODEL, temperature=0.3):
    """Send a list of {"role", "content"} messages, get back the reply text."""
    return complete(messages, model=model,
                    temperature=temperature).choices[0].message.content
