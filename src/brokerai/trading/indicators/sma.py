from __future__ import annotations

from typing import Any

from brokerai.trading.indicators._candles import candle_close, candle_time


def compute_sma(candles: list[dict[str, Any]], period: int) -> list[dict[str, Any]]:
    if not candles or period < 1:
        return []

    result: list[dict[str, Any]] = []
    window: list[float] = []

    for candle in candles:
        window.append(candle_close(candle))
        if len(window) > period:
            window.pop(0)
        if len(window) == period:
            result.append({"time": candle_time(candle), "value": sum(window) / period})

    return result
