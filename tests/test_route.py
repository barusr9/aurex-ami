"""Model routing (S6): the right model for each job.

pick_model is pure and cheap — it runs before the model, so it never calls
one. These tests pin the tier decisions and, crucially, that routing is OFF
by default (no cheap tier -> every turn uses the strong/default model, i.e.
no behaviour change until someone opts in).
"""

from types import SimpleNamespace

import pytest

from ami import route


def _cfg(cheap="", strong="", model="default-model"):
    """A stand-in config (the real one is a frozen dataclass). route.py only
    reads these three fields."""
    return SimpleNamespace(MODEL=model, MODEL_CHEAP=cheap, MODEL_STRONG=strong)


@pytest.fixture
def routing_on(monkeypatch):
    """Turn routing on with distinct tier names so we can tell them apart."""
    cfg = _cfg(cheap="cheap-model", strong="strong-model")
    monkeypatch.setattr(route, "config", cfg)
    return cfg


# --------------------------------------------------------------------------
# Off by default
# --------------------------------------------------------------------------

def test_routing_disabled_by_default_uses_one_model(monkeypatch):
    """With no cheap tier, every query returns the strong/default model."""
    monkeypatch.setattr(route, "config", _cfg(cheap="", strong="", model="default-model"))

    assert route.pick_model("what is your return policy?") == "default-model"
    assert route.pick_model("cancel my order 112-3333333-3333333") == "default-model"


# --------------------------------------------------------------------------
# When on: easy -> cheap, account/hard -> strong
# --------------------------------------------------------------------------

def test_simple_public_question_routes_cheap(routing_on):
    assert route.pick_model("what is your return policy?") == "cheap-model"


def test_private_account_query_routes_strong(routing_on):
    # "cancel my order" is PRIVATE -> account work -> strong model.
    assert route.pick_model("cancel my order 112-3333333-3333333") == "strong-model"


def test_long_public_question_routes_strong(routing_on):
    long_q = "I was wondering " + ("about your policies " * 20)   # > 200 chars
    assert len(long_q) > 200
    assert route.pick_model(long_q) == "strong-model"


def test_involved_public_question_routes_strong(routing_on):
    # a "compare / why / explain" style question is promoted even when short
    assert route.pick_model("why do you charge restocking fees?") == "strong-model"
    assert route.pick_model("compare standard and express shipping") == "strong-model"


def test_precomputed_query_type_is_honored(routing_on):
    # Passing query_type avoids reclassifying; PRIVATE forces strong.
    assert route.pick_model("short text", query_type="PRIVATE") == "strong-model"
    assert route.pick_model("short text", query_type="PUBLIC") == "cheap-model"


def test_strong_falls_back_to_default_when_no_strong_tier(monkeypatch):
    """Cheap set but no explicit strong tier -> strong uses MODEL."""
    monkeypatch.setattr(route, "config", _cfg(cheap="cheap-model", strong="", model="base-model"))

    assert route.pick_model("cancel my order", query_type="PRIVATE") == "base-model"
    assert route.pick_model("what is your return policy?") == "cheap-model"
