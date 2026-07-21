from __future__ import annotations

from typing import Any

from brokerai.trading.indicator_cache import IndicatorCacheView, indicator_cache_key
from brokerai.trading.indicators.adx import compute_adx
from brokerai.trading.indicators.at_time import atr_value_at_time, series_value_at_time
from brokerai.trading.indicators.atr import compute_atr
from brokerai.trading.registries.filters import register_filter
from brokerai.trading.risk_intent import is_jpy_quote_pair


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
        min_value = atr_min_value_for_pair(filter_spec, indicators.pair)
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
            "min_value_source": (
                "min_value_jpy"
                if is_jpy_quote_pair(indicators.pair) and filter_spec.get("min_value_jpy") is not None
                else "min_value"
            ),
        }
        return passed, metadata


def atr_min_value_for_pair(filter_spec: dict[str, Any], pair: str) -> float | None:
    """Return the ATR floor for *pair*.

    JPY-quote pairs use ``min_value_jpy`` when set; otherwise fall back to
    ``min_value`` so older strategies keep working. Non-JPY uses ``min_value``.
    """
    if is_jpy_quote_pair(pair):
        jpy = filter_spec.get("min_value_jpy")
        if jpy is not None:
            return float(jpy)
    min_value = filter_spec.get("min_value")
    if min_value is None:
        return None
    return float(min_value)


class HtfBiasFilterEvaluator:
    """Require entry direction to align with higher-timeframe EMA trend.

    Expects indicator cache series ``htf_ema:{tf}:fast`` and ``htf_ema:{tf}:slow``
    (closed HTF bars only). When series are missing, the filter fails closed.
    """

    filter_type = "htf_bias"

    def evaluate(
        self,
        filter_spec: dict[str, Any],
        candles: list[dict[str, Any]],
        indicators: IndicatorCacheView,
        direction: str | None,
        *,
        evaluate_at_time: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        _ = candles
        timeframe = str(filter_spec.get("timeframe", "H4"))
        fast_key = f"htf_ema:{timeframe}:fast"
        slow_key = f"htf_ema:{timeframe}:slow"
        fast = indicators.get_series(fast_key) or []
        slow = indicators.get_series(slow_key) or []
        if not fast or not slow:
            return False, {
                "timeframe": timeframe,
                "reason": "htf_data_unavailable",
                "direction": direction,
            }

        # Use last closed HTF point at or before evaluate_at_time when provided.
        fast_val = series_value_at_time(fast, evaluate_at_time)
        slow_val = series_value_at_time(slow, evaluate_at_time)
        if fast_val is None:
            fast_val = float(fast[-1]["value"])
        if slow_val is None:
            slow_val = float(slow[-1]["value"])

        bullish = fast_val > slow_val
        bearish = fast_val < slow_val
        if direction == "long":
            passed = bullish
        elif direction == "short":
            passed = bearish
        else:
            # No directional signal yet — do not block.
            passed = True

        return passed, {
            "timeframe": timeframe,
            "fast": fast_val,
            "slow": slow_val,
            "htf_bias": "bullish" if bullish else "bearish" if bearish else "flat",
            "direction": direction,
        }


def register_ema_crossover_filters() -> None:
    register_filter("adx", AdxFilterEvaluator())
    register_filter("atr", AtrFilterEvaluator())
    register_filter("htf_bias", HtfBiasFilterEvaluator())
