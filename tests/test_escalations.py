"""Escalation tickets: unique ids, a local record, optional delivery.

Tests pin:
- every hand-off gets its own ESC-<number>; numbers increase and survive a restart
- the id still matches the policy layer's identifier pattern (ESC-\\d+)
- the escalate tool returns the minted id and names the logged-in customer
- backend none: recorded, nothing sent
- webhook / email / jira: the record reaches the backend, the reference is stored
- a failing backend never raises; the failure is recorded and logged
"""

import io
import json
from types import SimpleNamespace

import pytest

from ami import escalations, observe, policy, tools


@pytest.fixture(autouse=True)
def tmp_tickets(tmp_state, tmp_path, monkeypatch):
    monkeypatch.setattr(escalations, "FILE", tmp_path / "state" / "escalations.jsonl")
    yield


def _cfg(**over):
    base = dict(ESCALATION_BACKEND="none", ESCALATION_TIMEOUT_SECONDS=2,
                ESCALATION_WEBHOOK_URL="", SMTP_HOST="", SMTP_PORT=587, SMTP_USER="",
                SMTP_PASSWORD="", ESCALATION_FROM="", ESCALATION_TO="",
                ESCALATION_EMAIL_CUSTOMER=False, JIRA_URL="", JIRA_EMAIL="",
                JIRA_API_TOKEN="", JIRA_PROJECT="", JIRA_ISSUE_TYPE="Task")
    base.update(over)
    return SimpleNamespace(**base)


def _lines():
    return [json.loads(l) for l in escalations.FILE.read_text().splitlines() if l.strip()]


class TestUniqueTickets:
    def test_each_ticket_is_new_and_increasing(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg())
        a = escalations.open_ticket("first")["ticket"]
        b = escalations.open_ticket("second")["ticket"]
        c = escalations.open_ticket("third")["ticket"]
        assert (a, b, c) == ("ESC-10001", "ESC-10002", "ESC-10003")

    def test_numbering_survives_a_restart(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg())
        escalations.open_ticket("before restart")
        escalations.open_ticket("before restart")
        # a "restart" is just a fresh read of the file: nothing is cached in memory
        assert escalations.open_ticket("after")["ticket"] == "ESC-10003"

    def test_id_matches_the_policy_identifier_pattern(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg())
        t = escalations.open_ticket("x")["ticket"]
        assert policy._IDENT.fullmatch(t)

    def test_record_is_written_with_customer_and_summary(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg())
        escalations.open_ticket("order 111 is late", customer="raj@example.com")
        rec = _lines()[-1]
        assert rec["ticket"] == "ESC-10001"
        assert rec["status"] == "opened"
        assert rec["customer"] == "raj@example.com"
        assert rec["summary"] == "order 111 is late"
        assert any(e["kind"] == "escalation" and e["status"] == "opened" for e in observe.EVENTS)

    def test_tickets_listing_folds_status(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg(ESCALATION_BACKEND="webhook",
                                                        ESCALATION_WEBHOOK_URL="https://hook"))
        monkeypatch.setattr(escalations.urllib.request, "urlopen", _fake_urlopen(status=200))
        rec = escalations.open_ticket("x"); escalations.deliver(rec)
        rec2 = escalations.open_ticket("y")
        listed = escalations.tickets()
        assert [t["ticket"] for t in listed] == [rec2["ticket"], rec["ticket"]]
        assert listed[1]["status"] == "delivered" and listed[1]["ref"] == "HTTP 200"
        assert listed[0]["status"] == "opened"


class TestEscalateTool:
    def test_two_customers_get_two_tickets(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg())
        r1 = tools.run("escalate", {"summary": "raj is unhappy"}, scope="raj@example.com")
        r2 = tools.run("escalate", {"summary": "mei is unhappy"}, scope="mei@example.com")
        assert r1["escalated"] and r2["escalated"]
        assert r1["ticket"] != r2["ticket"]
        assert r1["ticket"].startswith("ESC-") and r2["ticket"].startswith("ESC-")
        by = {l["ticket"]: l for l in _lines()}
        assert by[r1["ticket"]]["customer"] == "raj@example.com"
        assert by[r2["ticket"]]["customer"] == "mei@example.com"

    def test_tool_result_keeps_the_fields_the_planner_relies_on(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg())
        r = tools.run("escalate", {"summary": "x"})
        assert set(r) >= {"escalated", "ticket", "message", "summary"}
        assert "ref" not in r                      # no backend -> no external reference

    def test_unauthenticated_escalation_still_gets_a_ticket(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg())
        r = tools.run("escalate", {"summary": "cannot log in"})
        assert r["ticket"] == "ESC-10001"
        assert _lines()[-1]["customer"] is None


# --------------------------------------------------------------------------
# Backends, with the network faked
# --------------------------------------------------------------------------

class _Resp(io.BytesIO):
    def __init__(self, body=b"{}", status=200):
        super().__init__(body); self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _fake_urlopen(status=200, body=b"{}", capture=None, raise_=None):
    def urlopen(req, timeout=None):
        if capture is not None:
            capture.append({"url": req.full_url, "body": json.loads(req.data.decode()),
                            "headers": dict(req.headers), "timeout": timeout})
        if raise_:
            raise raise_
        return _Resp(body, status)
    return urlopen


class TestBackends:
    def test_none_sends_nothing(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg())
        called = []
        monkeypatch.setattr(escalations.urllib.request, "urlopen", _fake_urlopen(capture=called))
        rec = escalations.open_ticket("x")
        assert escalations.deliver(rec) is None
        assert called == []
        assert [l["status"] for l in _lines()] == ["opened"]

    def test_webhook_posts_the_record(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg(ESCALATION_BACKEND="webhook",
                                                        ESCALATION_WEBHOOK_URL="https://hooks.example/abc"))
        called = []
        monkeypatch.setattr(escalations.urllib.request, "urlopen", _fake_urlopen(capture=called))
        rec = escalations.open_ticket("late order", customer="raj@example.com")
        assert escalations.deliver(rec) == "HTTP 200"
        assert called[0]["url"] == "https://hooks.example/abc"
        assert called[0]["body"]["ticket"] == rec["ticket"]
        assert "raj@example.com" in called[0]["body"]["text"]
        assert called[0]["timeout"] == 2
        assert _lines()[-1]["status"] == "delivered"

    def test_jira_creates_an_issue_and_stores_the_key(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg(
            ESCALATION_BACKEND="jira", JIRA_URL="https://team.atlassian.net/",
            JIRA_EMAIL="me@example.com", JIRA_API_TOKEN="tok", JIRA_PROJECT="SUP"))
        called = []
        monkeypatch.setattr(escalations.urllib.request, "urlopen",
                            _fake_urlopen(body=b'{"key": "SUP-42"}', capture=called))
        rec = escalations.open_ticket("refund dispute", customer="mei@example.com")
        assert escalations.deliver(rec) == "SUP-42"
        c = called[0]
        assert c["url"] == "https://team.atlassian.net/rest/api/3/issue"
        assert c["body"]["fields"]["project"]["key"] == "SUP"
        assert c["body"]["fields"]["summary"].startswith(rec["ticket"])
        assert c["headers"]["Authorization"].startswith("Basic ")
        assert _lines()[-1]["ref"] == "SUP-42"

    def test_email_sends_to_support_and_optionally_the_customer(self, monkeypatch):
        sent = []

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                sent.append({"host": host, "port": port, "timeout": timeout})
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def starttls(self): sent[-1]["tls"] = True
            def login(self, u, p): sent[-1]["login"] = u
            def send_message(self, msg):
                sent[-1]["to"] = msg["To"]; sent[-1]["subject"] = msg["Subject"]

        monkeypatch.setattr(escalations.smtplib, "SMTP", FakeSMTP)
        monkeypatch.setattr(escalations, "config", _cfg(
            ESCALATION_BACKEND="email", SMTP_HOST="smtp.example.com", SMTP_USER="ami@example.com",
            SMTP_PASSWORD="pw", ESCALATION_TO="support@example.com", ESCALATION_EMAIL_CUSTOMER=True))
        rec = escalations.open_ticket("x", customer="raj@example.com")
        ref = escalations.deliver(rec)
        assert ref == "mail to support@example.com, raj@example.com"
        assert sent[0]["tls"] and sent[0]["login"] == "ami@example.com"
        assert sent[0]["to"] == "support@example.com, raj@example.com"
        assert rec["ticket"] in sent[0]["subject"]

    def test_failed_delivery_never_raises_and_is_recorded(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg(ESCALATION_BACKEND="webhook",
                                                        ESCALATION_WEBHOOK_URL="https://hooks.example/x"))
        monkeypatch.setattr(escalations.urllib.request, "urlopen",
                            _fake_urlopen(raise_=TimeoutError("timed out")))
        rec = escalations.open_ticket("x")
        assert escalations.deliver(rec) is None
        last = _lines()[-1]
        assert last["status"] == "delivery_failed" and "TimeoutError" in last["error"]
        assert any(e["kind"] == "escalation" and e["status"] == "delivery_failed" for e in observe.EVENTS)

    def test_misconfigured_backend_fails_soft(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg(ESCALATION_BACKEND="jira"))  # no URL/token
        rec = escalations.open_ticket("x")
        assert escalations.deliver(rec) is None
        assert "needs" in _lines()[-1]["error"]

    def test_unknown_backend_fails_soft(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg(ESCALATION_BACKEND="carrier-pigeon"))
        rec = escalations.open_ticket("x")
        assert escalations.deliver(rec) is None
        assert "unknown" in _lines()[-1]["error"]

    def test_tool_still_answers_when_the_backend_is_down(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg(ESCALATION_BACKEND="webhook",
                                                        ESCALATION_WEBHOOK_URL="https://hooks.example/x"))
        monkeypatch.setattr(escalations.urllib.request, "urlopen",
                            _fake_urlopen(raise_=ConnectionError("down")))
        r = tools.run("escalate", {"summary": "x"}, scope="raj@example.com")
        assert r["escalated"] and r["ticket"].startswith("ESC-") and "ref" not in r


class TestCustomerFacingTicket:
    """The customer is told the Jira key when Jira accepted the ticket."""

    def _jira_cfg(self):
        return _cfg(ESCALATION_BACKEND="jira", JIRA_URL="https://team.atlassian.net",
                    JIRA_EMAIL="me@example.com", JIRA_API_TOKEN="tok", JIRA_PROJECT="AMI")

    def test_jira_key_is_the_ticket_when_delivered(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", self._jira_cfg())
        monkeypatch.setattr(escalations.urllib.request, "urlopen",
                            _fake_urlopen(body=b'{"key": "AMI-7"}'))
        r = tools.run("escalate", {"summary": "late order"}, scope="raj@example.com")
        assert r["ticket"] == "AMI-7"
        assert r["local_ticket"].startswith("ESC-")
        assert _lines()[-1]["ref"] == "AMI-7"

    def test_falls_back_to_esc_when_jira_is_down(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", self._jira_cfg())
        monkeypatch.setattr(escalations.urllib.request, "urlopen",
                            _fake_urlopen(raise_=ConnectionError("down")))
        r = tools.run("escalate", {"summary": "late order"})
        assert r["ticket"] == r["local_ticket"] and r["ticket"].startswith("ESC-")

    def test_webhook_reference_is_not_mistaken_for_a_ticket(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg(ESCALATION_BACKEND="webhook",
                                                        ESCALATION_WEBHOOK_URL="https://hook"))
        monkeypatch.setattr(escalations.urllib.request, "urlopen", _fake_urlopen(status=200))
        r = tools.run("escalate", {"summary": "x"})
        assert r["ticket"].startswith("ESC-") and r["ref"] == "HTTP 200"

    def test_no_backend_keeps_esc(self, monkeypatch):
        monkeypatch.setattr(escalations, "config", _cfg())
        r = tools.run("escalate", {"summary": "x"})
        assert r["ticket"] == r["local_ticket"] == "ESC-10001"


class TestPolicyKnowsJiraKeys:
    def test_invented_jira_key_is_flagged_and_real_one_passes(self, monkeypatch):
        import re as _re
        monkeypatch.setattr("ami.config.config", _cfg(JIRA_PROJECT="AMI"))
        monkeypatch.setattr(policy, "_IDENT", policy._ident_pattern())
        from ami.memory import WorkingMemory
        w = WorkingMemory(scope="raj@example.com")
        w.record("escalate", {"summary": "x"}, {"escalated": True, "ticket": "AMI-7",
                                                 "message": "m", "summary": "x"})
        out = policy.check_output("Your ticket is AMI-7, not AMI-99.", w)
        assert "AMI-7" in out and "AMI-99" not in out and "[unverified]" in out
