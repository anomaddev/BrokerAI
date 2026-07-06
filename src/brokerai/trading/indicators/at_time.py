from __future__ import annotations

from datetime import datetime
from typing import Any

from brokerai.trading.analysis_runs import normalize_candle_time
from brokerai.trading.indicators.atr import compute_atr_series


def times_match(left: str | None, right: str | None) -> bool:
    """Compare candle/indicator timestamps from OANDA or ISO strings."""
    a = normalize_candle_time(left) if left else None
    b = normalize_candle_time(right) if right else None
    return a is not None and b is not None and a == b


def series_value_at_time(
    series: list[dict[str, Any]],
    time_key: str | None,
) -> float | None:
    """Return the indicator value at ``time_key``, or the latest when unset."""
    if not series:
        return None
    if not time_key:
        value = series[-1].get("value")
        return float(value) if value is not None else None

    target = normalize_candle_time(time_key)
    for point in series:
        point_time = normalize_candle_time(str(point.get("time") or ""))
        if target is not None and point_time == target:
            value = point.get("value")
            return float(value) if value is not None else None

    value = series[-1].get("value")
    return float(value) if value is not None else None


def atr_value_at_time(
    candles: list[dict[str, Any]],
    period: int,
    time_key: str | None,
) -> float | None:
    """ATR at a specific candle close (or latest when ``time_key`` is unset)."""
    series = compute_atr_series(candles, period)
    return series_value_at_time(series, time_key)
