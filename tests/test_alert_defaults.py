"""S2 / readout §6: the monitor ships ARMED.

A monitor whose thresholds default to 0 (off) is a demo. These pin the
shipped defaults to the thresholds the readout commits to, so a refactor
cannot silently disarm production monitoring, and prove they actually fire
through the real check_alerts path (not a stand-in config).
"""

import importlib

import pytest

from ami import observe


def _fresh_config(monkeypatch):
    """Re-import config with no ALERT_* env overrides -> the shipped defaults."""
    for k in ("ALERT_ERROR_RATE_PCT", "ALERT_COST_PER_TURN_USD", "ALERT_P95_MS"):
        monkeypatch.delenv(k, raising=False)
    import ami.config as cfgmod
    return importlib.reload(cfgmod).config


def test_shipped_defaults_are_armed_at_the_readout_thresholds(monkeypatch):
    cfg = _fresh_config(monkeypatch)
    assert cfg.ALERT_ERROR_RATE_PCT == 15
    assert cfg.ALERT_COST_PER_TURN_USD == 0.02
    assert cfg.ALERT_P95_MS == 12000


def test_defaults_actually_fire_through_check_alerts(monkeypatch):
    """Break it on purpose with the REAL defaults: all three must trip."""
    cfg = _fresh_config(monkeypatch)
    monkeypatch.setattr("ami.config.config", cfg)
    observe._firing.clear()

    bad = {"error_rate": 40, "cost_per_turn": 0.05, "turn_p95_ms": 20000}
    breached = set(observe.check_alerts(bad))

    assert breached == {"error_rate", "cost_per_turn", "turn_p95_ms"}
    kinds = [e for e in observe.EVENTS if e["kind"] == "alert" and e["state"] == "firing"]
    assert len(kinds) == 3
    observe._firing.clear()


def test_healthy_numbers_do_not_fire_with_defaults(monkeypatch):
    """Today's healthy readings sit under every default -> silence."""
    cfg = _fresh_config(monkeypatch)
    monkeypatch.setattr("ami.config.config", cfg)
    observe._firing.clear()

    ok = {"error_rate": 11, "cost_per_turn": 0.0105, "turn_p95_ms": 5500}
    assert observe.check_alerts(ok) == []


def test_zero_still_silences_an_alert(monkeypatch):
    """The off-switch survives: an operator can zero one threshold."""
    monkeypatch.setenv("ALERT_P95_MS", "0")
    import ami.config as cfgmod
    cfg = importlib.reload(cfgmod).config
    monkeypatch.setattr("ami.config.config", cfg)
    observe._firing.clear()

    assert "turn_p95_ms" not in observe.check_alerts(
        {"error_rate": 0, "cost_per_turn": 0, "turn_p95_ms": 999999})
    importlib.reload(cfgmod)   # restore module state for other tests
