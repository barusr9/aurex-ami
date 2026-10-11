"""Hand-off to a human requires login (confidentiality / governance)."""

import json

from ami import query_classifier as qc


def test_handoff_phrases_are_detected():
    for m in ["Connect me to a human", "I want to talk to someone", "get me a real person",
              "can I speak to a representative", "please escalate this", "live agent please"]:
        assert qc.is_handoff_request(m), m


def test_ordinary_questions_are_not_handoff():
    for m in ["what is the return window?", "where is my order 111-1111111-1111111",
              "do you ship to Canada?", "how do refunds work"]:
        assert not qc.is_handoff_request(m), m


def test_handoff_login_prompt_mentions_login_and_why():
    p = qc.get_handoff_login_prompt().lower()
    assert "log in" in p and "human" in p and "confidential" in p
