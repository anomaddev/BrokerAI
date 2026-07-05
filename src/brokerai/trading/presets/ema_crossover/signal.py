from __future__ import annotations

from typing import Any

from brokerai.strategies.candles import effective_min_candles
from brokerai.strategies.evaluator import StrategyResult
from brokerai.trading.indicator_cache import IndicatorCacheView, indicator_cache_key
from brokerai.trading.indicators.adx import compute_adx
from brokerai.trading.indicators.ema import compute_ema
from brokerai.trading.registries.signals import register_signal


def _series_at_time(series: list[dict[str, Any]], time_key: str) -> float | None:
    for point in series:
        if str(point.get("time")) == time_key:
            value = point.get("value")
            return float(value) if value is not None else None
    return None


def _detect_crossover(
    fast: list[dict[str, Any]],
    slow: list[dict[str, Any]],
    adx: list[dict[str, Any]],
    *,
    direction_filter: str,
    confirmation: str,
) -> tuple[str | None, float, dict[str, Any]]:
    """Detect an EMA crossover on the **current** (last) candle only.

    Live analysis runs when a new bar closes; a signal is emitted only when the
    crossover completes on that bar — the intended trade entry candle.
    """
    if len(fast) < 2:
        return None, 0.0, {"signal": "none"}

    slow_map = {str(point["time"]): float(point["value"]) for point in slow}
    adx_map = {str(point["time"]): float(point["value"]) for point in adx}

    index = len(fast) - 1
    time_key = str(fast[index]["time"])
    prev_time = str(fast[index - 1]["time"])
    curr_fast = float(fast[index]["value"])
    prev_fast = float(fast[index - 1]["value"])
    slow_val = slow_map.get(time_key)
    prev_slow = slow_map.get(prev_time)
    if slow_val is None or prev_slow is None:
        return None, 0.0, {"signal": "none"}

    bullish = prev_fast <= prev_slow and curr_fast > slow_val
    bearish = prev_fast >= prev_slow and curr_fast < slow_val
    if not bullish and not bearish:
        return None, 0.0, {"signal": "none"}

    signal_direction = "long" if bullish else "short"
    if direction_filter == "long" and signal_direction != "long":
        return None, 0.0, {"signal": "none"}
    if direction_filter == "short" and signal_direction != "short":
        return None, 0.0, {"signal": "none"}

    if confirmation == "pullback" and index < 2:
        return None, 0.0, {"signal": "none"}

    adx_val = adx_map.get(time_key, 20.0)
    confidence_pct = min(95.0, 50.0 + adx_val)
    metadata = {
        "signal": "bullish_cross" if bullish else "bearish_cross",
        "crossover_time": time_key,
        "adx": adx_val,
        "confirmation": confirmation,
    }
    return signal_direction, confidence_pct / 100.0, metadata


class EmaCrossoverSignalEvaluator:
    signal_type = "ema_crossover"

    def evaluate(
        self,
        candles: list[dict[str, Any]],
        params: dict[str, Any],
        indicators: IndicatorCacheView,
    ) -> StrategyResult:
        signal = params.get("signal") or {}
        indicators_spec = params.get("indicators") or {}
        fast_ref = str(signal.get("fast_ref", "fast"))
        slow_ref = str(signal.get("slow_ref", "slow"))
        fast_spec = indicators_spec.get(fast_ref) or {"type": "ema", "period": 9, "source": "close"}
        slow_spec = indicators_spec.get(slow_ref) or {"type": "ema", "period": 21, "source": "close"}

        fast_key = indicator_cache_key(
            str(fast_spec.get("type", "ema")),
            int(fast_spec.get("period", 9)),
            str(fast_spec.get("source", "close")),
        )
        slow_key = indicator_cache_key(
            str(slow_spec.get("type", "ema")),
            int(slow_spec.get("period", 21)),
            str(slow_spec.get("source", "close")),
        )

        fast = indicators.get_series(fast_key) or compute_ema(candles, int(fast_spec.get("period", 9)))
        slow = indicators.get_series(slow_key) or compute_ema(candles, int(slow_spec.get("period", 21)))

        adx_filter = next(
            (
                item
                for item in (params.get("filters") or [])
                if isinstance(item, dict) and item.get("type") == "adx" and item.get("enabled", True)
            ),
            None,
        )
        adx_period = int(adx_filter.get("period", 14)) if adx_filter else 14
        adx_key = indicator_cache_key("adx", adx_period)
        adx = indicators.get_series(adx_key) or compute_adx(candles, adx_period)

        direction, confidence, metadata = _detect_crossover(
            fast,
            slow,
            adx,
            direction_filter=str(signal.get("direction", "both")),
            confirmation=str(signal.get("confirmation", "close")),
        )

        return StrategyResult(
            confidence=confidence,
            min_candles=effective_min_candles(params),
            direction=direction,
            metadata=metadata,
        )


def register_ema_crossover_signal() -> None:
    register_signal("ema_crossover", EmaCrossoverSignalEvaluator())
