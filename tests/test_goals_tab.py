"""The /logs Goals tab: stats for goal 1 (cheaper and faster) and goal 2
(catch it when it breaks), and the read-only alert_status table.

Tests pin:
- cached_pct is the share of input tokens the proxy served from cache
- answer-cache hits/misses and prefetches are counted from their events
- per-turn ratios count web turns only; CLI eval events (turn "-") are excluded
- degraded turns are counted and expressed as a share of turns
- alert_status mirrors check_alerts thresholds without logging anything
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


def _web_turn(turn_id, llm_cost=0.004, cached=800, tokens_in=1000, degraded=False):
    """One web turn: a model call inside it, optionally a degraded hand-off."""
    observe.context(session="web-sess", turn=turn_id)
    observe.log("llm", model="m", ms=900, tokens=tokens_in + 50, tokens_in=tokens_in,
                tokens_out=50, cached=cached, cost=llm_cost)
    if degraded:
        observe.log("degraded", reason="model_error", step=1)
    observe.log("turn", user="hi", steps=1, ms=1200)


def _cli_eval_noise(n=5):
    """What an eval run leaves in the trace: model calls with no turn event."""
    observe.context(session="cli", turn="-")
    for _ in range(n):
        observe.log("llm", model="m", ms=500, tokens=1500, tokens_in=1400,
                    tokens_out=100, cached=0, cost=0.01)
    observe.log("degraded", reason="model_error", step=1)


class TestGoal1Stats:
    def test_cached_pct_is_share_of_input_tokens(self, tmp_state):
        _web_turn("t1", cached=800, tokens_in=1000)
        _web_turn("t2", cached=200, tokens_in=1000)
        s = observe.stats()
        assert s["cached_tokens"] == 1000
        assert s["cached_pct"] == 50

    def test_cache_hits_misses_and_prefetches_are_counted(self, tmp_state):
        observe.context(session="web-sess", turn="t1")
        observe.log("cache", result="hit")
        observe.log("cache", result="hit")
        observe.log("cache", result="miss")
        observe.log("prefetch", tool="get_order", order_id="111-1111111-1111111", ok=True)
        observe.log("turn", user="hi", steps=1, ms=900)          # prefetches count per web turn
        s = observe.stats()
        assert (s["cache_hits"], s["cache_misses"], s["prefetches"]) == (2, 1, 1)

    def test_prefetches_ignore_cli_eval_events(self, tmp_state):
        _web_turn("t1")
        observe.context(session="cli", turn="-")
        observe.log("prefetch", tool="get_order", order_id="112-3333333-3333333", ok=True)
        assert observe.stats()["prefetches"] == 0

    def test_per_turn_ratios_ignore_cli_eval_events(self, tmp_state):
        _web_turn("t1", llm_cost=0.004)
        _web_turn("t2", llm_cost=0.006)
        _cli_eval_noise(n=5)                      # 5 calls, $0.05, no turn events
        s = observe.stats()
        assert s["turns"] == 2
        assert s["calls_per_turn"] == 1.0         # not (2 + 5) / 2
        assert s["cost_per_turn_web"] == pytest.approx(0.005)

    def test_empty_trace_gives_zeros_not_errors(self, tmp_state):
        s = observe.stats()
        for k in ("calls_per_turn", "cost_per_turn_web", "cached_pct", "cache_hits",
                  "prefetches", "degraded_turns", "degraded_rate"):
            assert s[k] == 0


class TestGoal2Stats:
    def test_degraded_turns_and_rate(self, tmp_state):
        _web_turn("t1")
        _web_turn("t2", degraded=True)
        _web_turn("t3")
        _web_turn("t4", degraded=True)
        s = observe.stats()
        assert s["degraded_turns"] == 2
        assert s["degraded_rate"] == 50.0

    def test_degraded_rate_excludes_cli_eval_events(self, tmp_state):
        _web_turn("t1")
        _cli_eval_noise()                          # logs one degraded event with turn "-"
        s = observe.stats()
        assert s["degraded_turns"] == 1            # counted in the total
        assert s["degraded_rate"] == 0.0           # but not as a share of web turns


class TestAlertStatus:
    @pytest.fixture(autouse=True)
    def reset_firing(self):
        observe._firing.clear()
        yield
        observe._firing.clear()

    def test_one_row_per_configured_alert(self, tmp_state, monkeypatch):
        monkeypatch.setattr("ami.config.config", _cfg(error_rate=15, cost_per_turn=0.02, p95=12000))
        rows = observe.alert_status()
        assert [r["metric"] for r in rows] == ["error_rate", "cost_per_turn", "turn_p95_ms"]
        assert all(r["enabled"] for r in rows)
        assert not any(r["firing"] for r in rows)

    def test_breach_shows_as_firing_without_logging(self, tmp_state, monkeypatch):
        monkeypatch.setattr("ami.config.config", _cfg(p95=1000))
        _web_turn("t1")                            # the turn took 1200 ms
        before = len([e for e in observe.EVENTS if e["kind"] == "alert"])
        rows = {r["metric"]: r for r in observe.alert_status()}
        assert rows["turn_p95_ms"]["firing"] is True
        assert rows["turn_p95_ms"]["value"] == 1200
        after = len([e for e in observe.EVENTS if e["kind"] == "alert"])
        assert after == before                     # read-only: check_alerts logs, this does not

    def test_zero_threshold_is_reported_disabled(self, tmp_state, monkeypatch):
        monkeypatch.setattr("ami.config.config", _cfg())
        rows = observe.alert_status()
        assert all(r["enabled"] is False and r["firing"] is False for r in rows)
