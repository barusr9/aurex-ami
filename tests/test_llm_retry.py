"""llm._call gives up on a persistent gateway error inside its time budget
instead of retrying for many minutes (the injection eval case hung ~14 min)."""

import httpx
import pytest
from openai import APIStatusError

from ami import llm


def _status_error(code):
    req = httpx.Request("POST", "http://proxy/v1/chat/completions")
    return APIStatusError("bad gateway", response=httpx.Response(code, request=req), body=None)


def test_persistent_502_fails_within_the_retry_budget(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(llm.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    calls = []

    def always_502(**kw):
        calls.append(1)
        raise _status_error(502)
    monkeypatch.setattr(llm._client.chat.completions, "create", always_502)

    with pytest.raises(APIStatusError):
        llm._call({"model": "m", "messages": []})
    assert clock["t"] <= llm.config.LLM_GATEWAY_RETRY_SECONDS  # gateway errors: the short budget
    assert len(calls) <= llm.RATE_LIMIT_TRIES


def test_client_does_not_retry_on_its_own():
    assert llm._client.max_retries == 0
