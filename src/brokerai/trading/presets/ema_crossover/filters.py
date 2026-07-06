from __future__ import annotations

from typing import Any

from brokerai.trading.indicator_cache import IndicatorCacheView, indicator_cache_key
from brokerai.trading.indicators.adx import compute_adx
from brokerai.trading.indicators.at_time import atr_value_at_time, series_value_at_time
from brokerai.trading.indicators.atr import compute_atr
from brokerai.trading.registries.filters import register_filter


def _compare(value: float, threshold: float, operator: str) -> bool:
    if operator == "gte":
        return value >= threshold
    if operator == "lte":
        return value <= threshold
    if operator == "gt":
        return value > threshold
    if operator == "lt":
        return value < threshold
    if operator == "eq":
        return value == threshold
    return value >= threshold


class AdxFilterEvaluator:
    filter_type = "adx"

    def evaluate(
        self,
        filter_spec: dict[str, Any],
        candles: list[dict[str, Any]],
        indicators: IndicatorCacheView,
        direction: str | None,
        *,
        evaluate_at_time: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        _ = direction
        period = int(filter_spec.get("period", 14))
        threshold = float(filter_spec.get("threshold", 25))
        compare = str(filter_spec.get("compare", "gte"))
        key = indicator_cache_key("adx", period)
        series = indicators.get_series(key) or compute_adx(candles, period)
        if not series:
            return False, {"adx": None, "reason": "insufficient_data"}
        adx_val = series_value_at_time(series, evaluate_at_time)
        if adx_val is None:
            return False, {"adx": None, "reason": "insufficient_data"}
        passed = _compare(adx_val, threshold, compare)
        metadata: dict[str, Any] = {
            "adx": adx_val,
            "threshold": threshold,
            "compare": compare,
        }
        return passed, metadata


class AtrFilterEvaluator:
    filter_type = "atr"

    def evaluate(
        self,
        filter_spec: dict[str, Any],
        candles: list[dict[str, Any]],
        indicators: IndicatorCacheView,
        direction: str | None,
        *,
        evaluate_at_time: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        _ = direction
        period = int(filter_spec.get("period", 14))
        key = indicator_cache_key("atr", period)
        atr_val = None
        if evaluate_at_time:
            atr_val = atr_value_at_time(candles, period, evaluate_at_time)
        if atr_val is None:
            atr_val = indicators.get_scalar(key)
        if atr_val is None:
            atr_val = compute_atr(candles, period)
        min_value = filter_spec.get("min_value")
        max_value = filter_spec.get("max_value")
        passed = True
        if min_value is not None and atr_val < float(min_value):
            passed = False
        if max_value is not None and atr_val > float(max_value):
            passed = False
        metadata: dict[str, Any] = {
            "atr": atr_val,
            "min_value": min_value,
            "max_value": max_value,
        }
        return passed, metadata


def register_ema_crossover_filters() -> None:
    register_filter("adx", AdxFilterEvaluator())
    register_filter("atr", AtrFilterEvaluator())
