"""Helpers to warm higher-timeframe EMA series for the htf_bias filter."""

from __future__ import annotations

from typing import Any

from brokerai.trading.indicator_cache import IndicatorCacheView
from brokerai.trading.indicators.ema import compute_ema


def htf_bias_filter_spec(params: dict[str, Any]) -> dict[str, Any] | None:
    for item in params.get("filters") or []:
        if (
            isinstance(item, dict)
            and item.get("type") == "htf_bias"
            and item.get("enabled", True)
        ):
            return item
    return None


def attach_htf_ema_series(
    view: IndicatorCacheView,
    *,
    timeframe: str,
    candles: list[dict[str, Any]],
    fast_period: int = 9,
    slow_period: int = 21,
) -> IndicatorCacheView:
    """Mutate ``view`` with closed-bar HTF EMA series used by ``HtfBiasFilterEvaluator``."""
    if not candles:
        return view
    fast = compute_ema(candles, fast_period)
    slow = compute_ema(candles, slow_period)
    view._values[f"htf_ema:{timeframe}:fast"] = fast
    view._values[f"htf_ema:{timeframe}:slow"] = slow
    return view


def signal_ema_periods(params: dict[str, Any]) -> tuple[int, int]:
    signal = params.get("signal") or {}
    indicators = params.get("indicators") or {}
    fast_ref = str(signal.get("fast_ref", "fast"))
    slow_ref = str(signal.get("slow_ref", "slow"))
    fast_spec = indicators.get(fast_ref) or {"period": 9}
    slow_spec = indicators.get(slow_ref) or {"period": 21}
    return int(fast_spec.get("period", 9)), int(slow_spec.get("period", 21))
