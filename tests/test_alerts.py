"""Regression monitor (S2): a metric that gets worse trips a visible alert.

check_alerts() compares live stats against the configured thresholds and
logs a distinct `alert` event on the transition into breach (and a recovery
when it clears) — not once per check, so a sustained problem doesn't bury
the trace.

This is also the "break on purpose" proof: we deliberately push a metric
past its threshold and assert the monitor catches it.
"""

from types import SimpleNamespace

import pytest

from ami import observe


def _cfg(error_rate=0, cost_per_turn=0.0, p95=0):
    return SimpleNamespace(
        ALERT_ERROR_RATE_PCT=error_rate,
        ALERT_COST_PER_TURN_USD=cost_per_turn,
        ALERT_P95_MS=p95,
    )


@pytest.fixture(autouse=True)
def reset_firing():
    """Each test starts with no alerts currently firing."""
    observe._firing.clear()
    yield
    observe._firing.clear()


def _alerts_in_trace():
    return [e for e in observe.EVENTS if e["kind"] == "alert"]


# --------------------------------------------------------------------------
# Disabled by default
# --------------------------------------------------------------------------

def test_no_alerts_when_thresholds_are_zero(monkeypatch):
    monkeypatch.setattr("ami.config.config", _cfg())      # all 0 = disabled
    breached = observe.check_alerts({"error_rate": 99, "cost_per_turn": 9.0,
                                     "turn_p95_ms": 999999})
    assert breached == []
    assert _alerts_in_trace() == []


# --------------------------------------------------------------------------
# Break on purpose
# --------------------------------------------------------------------------

def test_error_rate_breach_fires_one_alert(monkeypatch):
    monkeypatch.setattr("ami.config.config", _cfg(error_rate=10))
    stats = {"error_rate": 25, "cost_per_turn": 0, "turn_p95_ms": 0}

    breached = observe.check_alerts(stats)
    assert "error_rate" in breached

    alerts = _alerts_in_trace()
    assert len(alerts) == 1
    assert alerts[0]["metric"] == "error_rate"
    assert alerts[0]["state"] == "firing"
    assert alerts[0]["value"] == 25


def test_alert_fires_once_then_recovers(monkeypatch):
    monkeypatch.setattr("ami.config.config", _cfg(cost_per_turn=0.05))

    bad = {"error_rate": 0, "cost_per_turn": 0.10, "turn_p95_ms": 0}
    good = {"error_rate": 0, "cost_per_turn": 0.01, "turn_p95_ms": 0}

    observe.check_alerts(bad)      # fires
    observe.check_alerts(bad)      # still breached — must NOT fire again
    observe.check_alerts(good)     # recovers

    alerts = _alerts_in_trace()
    states = [a["state"] for a in alerts if a["metric"] == "cost_per_turn"]
    assert states == ["firing", "recovered"]


def test_multiple_metrics_breach_independently(monkeypatch):
    monkeypatch.setattr("ami.config.config",
                        _cfg(error_rate=10, p95=1000))
    stats = {"error_rate": 50, "cost_per_turn": 0, "turn_p95_ms": 5000}

    breached = set(observe.check_alerts(stats))
    assert breached == {"error_rate", "turn_p95_ms"}
    assert len(_alerts_in_trace()) == 2
