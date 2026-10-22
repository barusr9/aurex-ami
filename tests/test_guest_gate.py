"""Guest gate: general questions reach the agent; only plain account
references are stopped up front. Account tools refuse a guest themselves."""

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import web
from ami import query_classifier as qc
from ami import tools

GENERAL = [
    "tell me when can i return a product?",          # the case that started this
    "what is the return window?",
    "how many days do i have to return?",
    "can i get a refund on a gift?",
    "what is the eta for prime shipping?",
    "give me details about the warranty",            # "details" contains "eta"
    "is creating an account free?",
    "how do refunds work",
    "what is my return policy",                      # "my return" + policy is still general
    "what are my refund options?",
]

ACCOUNT = [
    "where is my order?",
    "what's the status of 112-3333333-3333333",
    "cancel order 111-1111111-1111111",
    "show me my account",
    "when will my refund arrive",
    "track my package",
    "I want to start my return",
    "where is my return?",
    "my refund policy says 30 days but my refund is late",   # still names their refund
    "change my address",
]


@pytest.mark.parametrize("msg", GENERAL)
def test_general_questions_pass_the_gate(msg):
    assert not qc.needs_login_upfront(msg)


@pytest.mark.parametrize("msg", ACCOUNT)
def test_account_references_are_gated(msg):
    assert qc.needs_login_upfront(msg)


def test_classify_query_stays_broad_for_routing_and_cache():
    # The shared answer cache must never serve these, so they stay PRIVATE.
    assert qc.classify_query("tell me when can i return a product?") == "PRIVATE"


@pytest.mark.parametrize("name,args", [
    ("find_orders", {}),
    ("get_order", {"order_id": "111-1111111-1111111"}),
    ("track_package", {"order_id": "111-1111111-1111111"}),
    ("cancel_order", {"order_id": "111-1111111-1111111"}),
    ("start_return", {"order_id": "111-1111111-1111111", "reason": "x"}),
])
def test_account_tools_refuse_a_guest_with_login_required(name, args):
    r = tools.run(name, args, scope=None)
    assert "error" in r and r.get("login_required") is True


class TestWeb:
    @pytest.fixture
    def server(self, monkeypatch):
        calls = []

        def fake_answer(text, query_type, convo, work, run):
            calls.append(text)
            return "Most items can be returned within 30 days of delivery.", False

        monkeypatch.setattr(web.answer_cache, "answer", fake_answer)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{srv.server_address[1]}", calls
        srv.shutdown()

    def _chat(self, url, message):
        req = urllib.request.Request(url + "/chat", data=json.dumps({"message": message}).encode(),
                                     method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_guest_general_question_reaches_the_agent(self, server):
        url, calls = server
        d = self._chat(url, "tell me when can i return a product?")
        assert calls == ["tell me when can i return a product?"]
        assert "30 days" in d["reply"]
        assert not d.get("requires_login") and not d.get("gated")

    def test_guest_order_number_is_gated_without_the_agent(self, server):
        url, calls = server
        d = self._chat(url, "what's the status of 112-3333333-3333333?")
        assert calls == []
        assert d["requires_login"] and d["gated"] and d["steps"] == []
