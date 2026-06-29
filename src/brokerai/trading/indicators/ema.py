from __future__ import annotations

from typing import Any

from brokerai.trading.indicators._candles import candle_close, candle_time


def compute_ema(candles: list[dict[str, Any]], period: int) -> list[dict[str, Any]]:
    if not candles or period < 1:
        return []

    k = 2 / (period + 1)
    result: list[dict[str, Any]] = []
    ema = candle_close(candles[0])

    for index, candle in enumerate(candles):
        close = candle_close(candle)
        ema = close if index == 0 else close * k + ema * (1 - k)
        if index >= period - 1:
            result.append({"time": candle_time(candle), "value": ema})

    return result
