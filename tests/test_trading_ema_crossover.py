from tests.fixtures.mock_candles import generate_mock_candles
import pytest
from brokerai.trading.indicator_cache import IndicatorCache
from brokerai.trading.pipeline import run_strategy_analysis
from brokerai.trading.presets.ema_crossover import register_ema_crossover


def _ema_strategy_params() -> dict:
    return {
        "timeframe": "M15",
        "min_candles": 63,
        "indicators": {
            "fast": {"type": "ema", "period": 9, "source": "close"},
            "slow": {"type": "ema", "period": 21, "source": "close"},
        },
        "signal": {
            "type": "ema_crossover",
            "fast_ref": "fast",
            "slow_ref": "slow",
            "direction": "both",
            "confirmation": "close",
        },
        "filters": [
            {
                "id": "adx",
                "type": "adx",
                "enabled": True,
                "period": 14,
                "threshold": 15,
                "compare": "gte",
            },
            {
                "id": "atr",
                "type": "atr",
                "enabled": True,
                "period": 14,
                "min_value": 0.0008,
            },
        ],
        "exits": {
            "stop_loss": {"mode": "atr_based", "atr_multiplier": 1.5},
            "take_profit": {"mode": "rr_ratio", "risk_reward_ratio": 2.0},
        },
        "risk": {"risk_per_trade_pct": 1.0, "max_trades_per_day": 3},
        "execution": {
            "sessions": ["London"],
            "min_confidence": 0,
            "override_all_strategies": False,
            "priority": 50,
        },
    }


async def test_run_strategy_analysis_returns_result():
    register_ema_crossover()
    candles = generate_mock_candles(120)
    strategy = {
        "id": "test-strategy",
        "name": "Test EMA",
        "timeframe": "M15",
        "preset_id": "ema_crossover",
        "params": _ema_strategy_params(),
    }
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [strategy["params"]])
    result = await run_strategy_analysis(strategy, "EUR/USD", candles, cache, timeframe="M15")

    assert result.strategy_id == "test-strategy"
    assert result.pair == "EUR/USD"
    assert 0.0 <= result.confidence <= 1.0
    assert result.min_candles >= 21


def test_filters_evaluated_at_crossover_time():
    from brokerai.trading.indicator_cache import IndicatorCacheView
    from brokerai.trading.presets.ema_crossover import register_ema_crossover
    from brokerai.trading.registries.filters import run_filter_chain

    register_ema_crossover()
    crossover_time = "2026-07-06T04:45:00.000000000Z"
    latest_time = "2026-07-06T06:00:00.000000000Z"
    adx_series = [
        {"time": crossover_time, "value": 28.0},
        {"time": latest_time, "value": 18.5},
    ]
    indicators = IndicatorCacheView(
        pair="AUD/CHF",
        timeframe="M15",
        _values={"adx:14:close": adx_series},
    )
    filters = [
        {
            "id": "adx",
            "type": "adx",
            "enabled": True,
            "period": 14,
            "threshold": 25,
            "compare": "gte",
        }
    ]

    passed_latest, latest_meta = run_filter_chain(
        filters,
        candles=[],
        indicators=indicators,
        direction="long",
    )
    passed_cross, cross_meta = run_filter_chain(
        filters,
        candles=[],
        indicators=indicators,
        direction="long",
        evaluate_at_time=crossover_time,
    )

    assert passed_latest is False
    assert latest_meta["adx"]["adx"] == 18.5
    assert passed_cross is True
    assert cross_meta["adx"]["adx"] == 28.0


async def test_filter_chain_can_block_signal():
    register_ema_crossover()
    candles = generate_mock_candles(120)
    params = _ema_strategy_params()
    params["filters"][1]["min_value"] = 0.005
    strategy = {
        "id": "blocked",
        "name": "Blocked",
        "timeframe": "M15",
        "preset_id": "ema_crossover",
        "params": params,
    }
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [params])
    result = await run_strategy_analysis(strategy, "EUR/USD", candles, cache, timeframe="M15")
    assert result.metadata.get("filters_passed") is False
    if result.direction is not None:
        assert result.confidence > 0


async def test_run_strategy_analysis_rejects_insufficient_candles():
    register_ema_crossover()
    candles = generate_mock_candles(10)
    strategy = {
        "id": "short-cache",
        "name": "Short Cache",
        "timeframe": "M15",
        "preset_id": "ema_crossover",
        "params": _ema_strategy_params(),
    }
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [strategy["params"]])
    result = await run_strategy_analysis(strategy, "EUR/USD", candles, cache, timeframe="M15")

    assert result.direction is None
    assert result.confidence == 0.0
    assert result.metadata.get("reason") == "insufficient_candles"
    assert result.metadata.get("have") == 10
    assert result.metadata.get("need", 0) >= 63


def test_detect_crossover_only_on_current_candle():
    from brokerai.trading.presets.ema_crossover.signal import _detect_crossover

    fast = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.0},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.0},
        {"time": "2026-01-01T00:30:00+00:00", "value": 2.0},
    ]
    slow = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.5},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.5},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.5},
    ]

    direction, confidence, metadata = _detect_crossover(
        fast,
        slow,
        [],
        direction_filter="both",
        confirmation="close",
    )

    assert direction == "long"
    assert confidence > 0
    assert metadata["signal"] == "bullish_cross"
    assert metadata["crossover_time"] == "2026-01-01T00:30:00+00:00"


def test_detect_crossover_catchup_finds_recent_historical_cross():
    from brokerai.trading.presets.ema_crossover.signal import _detect_crossover

    fast = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.0},
        {"time": "2026-01-01T00:15:00+00:00", "value": 2.0},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.8},
    ]
    slow = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.5},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.5},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.5},
    ]

    direction, confidence, metadata = _detect_crossover(
        fast,
        slow,
        [],
        direction_filter="both",
        confirmation="close",
        catchup=True,
    )

    assert direction == "long"
    assert confidence > 0
    assert metadata["signal"] == "bullish_cross"
    assert metadata["crossover_time"] == "2026-01-01T00:15:00+00:00"
    assert metadata.get("catchup") is True


def test_detect_crossover_ignores_historical_cross():
    from brokerai.trading.presets.ema_crossover.signal import _detect_crossover

    fast = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 2.0},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.0},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.2},
    ]
    slow = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.5},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.5},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.5},
    ]

    direction, confidence, metadata = _detect_crossover(
        fast,
        slow,
        [],
        direction_filter="both",
        confirmation="close",
    )

    assert direction is None
    assert confidence == 0.0
    assert metadata["signal"] == "none"


def _approaching_bullish_series() -> tuple[list, list, list, list]:
    """Fast EMA rising toward slow with narrowing gap on the last three bars."""
    fast = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.480},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.488},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.494},
    ]
    slow = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.500},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.499},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.498},
    ]
    adx = [{"time": "2026-01-01T00:30:00+00:00", "value": 24.0}]
    atr = [{"time": "2026-01-01T00:30:00+00:00", "value": 0.01}]
    return fast, slow, adx, atr


def test_detect_approaching_bullish_convergence():
    from brokerai.trading.presets.ema_crossover.signal import _detect_approaching

    fast, slow, adx, atr = _approaching_bullish_series()
    direction, confidence, metadata = _detect_approaching(
        fast,
        slow,
        adx,
        atr,
        direction_filter="both",
        confirmation="close",
        max_gap_atr=0.5,
        min_narrow_bars=2,
    )

    assert direction == "long"
    assert 0 < confidence <= 0.75
    assert metadata["signal"] == "approaching_bullish_cross"
    assert metadata["signal_time"] == "2026-01-01T00:30:00+00:00"
    assert metadata["convergence_bars"] == 2
    assert metadata["ema_gap"] == pytest.approx(0.004)
    assert metadata["ema_gap_atr"] == pytest.approx(0.4)


def test_detect_approaching_bearish_convergence():
    from brokerai.trading.presets.ema_crossover.signal import _detect_approaching

    fast = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.520},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.512},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.506},
    ]
    slow = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.500},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.501},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.502},
    ]
    adx = [{"time": "2026-01-01T00:30:00+00:00", "value": 22.0}]
    atr = [{"time": "2026-01-01T00:30:00+00:00", "value": 0.01}]

    direction, confidence, metadata = _detect_approaching(
        fast,
        slow,
        adx,
        atr,
        direction_filter="both",
        confirmation="close",
    )

    assert direction == "short"
    assert confidence > 0
    assert metadata["signal"] == "approaching_bearish_cross"


def test_detect_approaching_rejects_gap_too_wide():
    from brokerai.trading.presets.ema_crossover.signal import _detect_approaching

    fast, slow, adx, atr = _approaching_bullish_series()
    direction, confidence, metadata = _detect_approaching(
        fast,
        slow,
        adx,
        atr,
        direction_filter="both",
        confirmation="close",
        max_gap_atr=0.2,
    )

    assert direction is None
    assert metadata["signal"] == "none"


def test_detect_approaching_rejects_non_narrowing_gap():
    from brokerai.trading.presets.ema_crossover.signal import _detect_approaching

    fast = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.480},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.488},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.490},
    ]
    slow = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.500},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.499},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.498},
    ]
    adx = [{"time": "2026-01-01T00:30:00+00:00", "value": 24.0}]
    atr = [{"time": "2026-01-01T00:30:00+00:00", "value": 0.01}]

    direction, _, metadata = _detect_approaching(
        fast,
        slow,
        adx,
        atr,
        direction_filter="both",
        confirmation="close",
    )

    assert direction is None
    assert metadata["signal"] == "none"


def test_detect_approaching_respects_direction_filter():
    from brokerai.trading.presets.ema_crossover.signal import _detect_approaching

    fast, slow, adx, atr = _approaching_bullish_series()
    direction, _, metadata = _detect_approaching(
        fast,
        slow,
        adx,
        atr,
        direction_filter="short",
        confirmation="close",
    )

    assert direction is None
    assert metadata["signal"] == "none"


def test_detect_crossover_takes_priority_over_approaching():
    from brokerai.trading.presets.ema_crossover.signal import (
        EmaCrossoverSignalEvaluator,
    )

    fast = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.480},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.488},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.500},
    ]
    slow = [
        {"time": "2026-01-01T00:00:00+00:00", "value": 1.500},
        {"time": "2026-01-01T00:15:00+00:00", "value": 1.499},
        {"time": "2026-01-01T00:30:00+00:00", "value": 1.498},
    ]
    candles = [{"time": point["time"], "close": point["value"]} for point in fast]
    params = _ema_strategy_params()

    class StubIndicators:
        def get_series(self, key):
            if key == "ema:9:close":
                return fast
            if key == "ema:21:close":
                return slow
            if key == "adx:14:close":
                return [{"time": "2026-01-01T00:30:00+00:00", "value": 24.0}]
            if key == "atr:14:close":
                return [{"time": "2026-01-01T00:30:00+00:00", "value": 0.01}]
            return None

    result = EmaCrossoverSignalEvaluator().evaluate(
        candles,
        params,
        StubIndicators(),  # type: ignore[arg-type]
    )

    assert result.metadata["signal"] == "bullish_cross"
    assert "approach" not in result.metadata["signal"]


def test_filters_evaluated_at_approaching_signal_time():
    from brokerai.trading.indicator_cache import IndicatorCacheView
    from brokerai.trading.registries.filters import run_filter_chain

    register_ema_crossover()
    signal_time = "2026-07-06T06:00:00.000000000Z"
    latest_time = "2026-07-06T06:15:00.000000000Z"
    adx_series = [
        {"time": signal_time, "value": 28.0},
        {"time": latest_time, "value": 18.5},
    ]
    indicators = IndicatorCacheView(
        pair="AUD/CHF",
        timeframe="M15",
        _values={"adx:14:close": adx_series},
    )
    filters = [
        {
            "id": "adx",
            "type": "adx",
            "enabled": True,
            "period": 14,
            "threshold": 25,
            "compare": "gte",
        }
    ]

    passed_latest, _ = run_filter_chain(
        filters,
        candles=[],
        indicators=indicators,
        direction="long",
    )
    passed_signal, signal_meta = run_filter_chain(
        filters,
        candles=[],
        indicators=indicators,
        direction="long",
        evaluate_at_time=signal_time,
    )

    assert passed_latest is False
    assert passed_signal is True
    assert signal_meta["adx"]["adx"] == 28.0
