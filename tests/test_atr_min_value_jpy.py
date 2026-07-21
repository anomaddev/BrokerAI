"""Tests for pair-aware ATR min floor (JPY vs non-JPY)."""

from __future__ import annotations

from brokerai.trading.indicator_cache import IndicatorCacheView
from brokerai.trading.presets.ema_crossover.filters import (
    AtrFilterEvaluator,
    atr_min_value_for_pair,
)


def test_atr_min_value_for_pair_uses_jpy_when_set():
    spec = {"min_value": 0.0008, "min_value_jpy": 0.05}
    assert atr_min_value_for_pair(spec, "EUR/USD") == 0.0008
    assert atr_min_value_for_pair(spec, "USD/JPY") == 0.05
    assert atr_min_value_for_pair(spec, "EUR_JPY") == 0.05


def test_atr_min_value_for_pair_falls_back_when_jpy_omitted():
    spec = {"min_value": 0.0008}
    assert atr_min_value_for_pair(spec, "USD/JPY") == 0.0008


def test_atr_filter_evaluator_applies_jpy_floor():
    evaluator = AtrFilterEvaluator()
    candles = [
        {
            "time": f"2026-07-20T12:{i:02d}:00.000000000Z",
            "open": 150.0,
            "high": 150.02,
            "low": 149.98,
            "close": 150.0,
            "volume": 1,
        }
        for i in range(20)
    ]
    # Low ATR environment (~0.02); JPY floor 0.05 should fail, EUR floor 0.0008 pass.
    view_jpy = IndicatorCacheView(pair="USD/JPY", timeframe="M15", _values={})
    passed_jpy, meta_jpy = evaluator.evaluate(
        {"type": "atr", "enabled": True, "period": 14, "min_value": 0.0008, "min_value_jpy": 0.05},
        candles,
        view_jpy,
        "long",
    )
    assert passed_jpy is False
    assert meta_jpy["min_value"] == 0.05
    assert meta_jpy["min_value_source"] == "min_value_jpy"

    view_eur = IndicatorCacheView(pair="EUR/USD", timeframe="M15", _values={})
    passed_eur, meta_eur = evaluator.evaluate(
        {"type": "atr", "enabled": True, "period": 14, "min_value": 0.0008, "min_value_jpy": 0.05},
        candles,
        view_eur,
        "long",
    )
    assert passed_eur is True
    assert meta_eur["min_value"] == 0.0008
    assert meta_eur["min_value_source"] == "min_value"
