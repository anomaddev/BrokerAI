"""Tests for higher-timeframe EMA bias filter."""

from __future__ import annotations

from brokerai.trading.indicator_cache import IndicatorCacheView
from brokerai.trading.presets.ema_crossover.filters import HtfBiasFilterEvaluator
from brokerai.trading.presets.ema_crossover.htf_bias import attach_htf_ema_series


def _candle(time: str, close: float) -> dict:
    return {
        "time": time,
        "open": close,
        "high": close + 0.1,
        "low": close - 0.1,
        "close": close,
        "volume": 1,
    }


def test_htf_bias_fails_closed_without_series():
    evaluator = HtfBiasFilterEvaluator()
    view = IndicatorCacheView(pair="USD/JPY", timeframe="M15", _values={})
    passed, meta = evaluator.evaluate(
        {"type": "htf_bias", "enabled": True, "timeframe": "H4"},
        [],
        view,
        "long",
    )
    assert passed is False
    assert meta["reason"] == "htf_data_unavailable"


def test_htf_bias_requires_long_when_htf_bullish():
    candles = [
        _candle(f"2026-07-20T{hour:02d}:00:00.000000000Z", 150.0 + hour * 0.2)
        for hour in range(40)
    ]
    view = IndicatorCacheView(pair="USD/JPY", timeframe="H4", _values={})
    attach_htf_ema_series(view, timeframe="H4", candles=candles, fast_period=3, slow_period=8)
    evaluator = HtfBiasFilterEvaluator()
    passed_long, meta = evaluator.evaluate(
        {"type": "htf_bias", "enabled": True, "timeframe": "H4"},
        candles,
        view,
        "long",
    )
    passed_short, _ = evaluator.evaluate(
        {"type": "htf_bias", "enabled": True, "timeframe": "H4"},
        candles,
        view,
        "short",
    )
    assert meta["htf_bias"] == "bullish"
    assert passed_long is True
    assert passed_short is False
