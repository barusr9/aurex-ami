"""The single place where we talk to the model.

Reads OPENAI_API_KEY and OPENAI_BASE_URL from .env. The base URL points at
the class LLM proxy, which speaks the OpenAI chat-completions API.
"""

import os
import time

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIStatusError

from ami import observe
from ami import pricing
from ami.config import config

load_dotenv()

# Model and retry budget come from config (one source of truth); the env
# vars they read still work exactly as before.
MODEL = config.MODEL

_client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ["OPENAI_BASE_URL"],
)


RATE_LIMIT_TRIES = config.LLM_RETRY_TRIES

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
    for attempt in range(RATE_LIMIT_TRIES):
        try:
            return _client.chat.completions.create(**kwargs)
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
