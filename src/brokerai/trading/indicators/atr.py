from __future__ import annotations

from typing import Any

from brokerai.trading.indicators._candles import candle_close


def compute_atr(candles: list[dict[str, Any]], period: int) -> float:
    if len(candles) < period + 1:
        return 0.001

    total = 0.0
    for index in range(len(candles) - period, len(candles)):
        prev_close = candle_close(candles[index - 1])
        high = float(candles[index]["high"])
        low = float(candles[index]["low"])
        true_range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        total += true_range

    return total / period


def compute_atr_series(candles: list[dict[str, Any]], period: int) -> list[dict[str, Any]]:
    if len(candles) < period + 1:
        return []

    from brokerai.trading.indicators._candles import candle_time

    result: list[dict[str, Any]] = []
    for index in range(period, len(candles)):
        window = candles[index - period + 1 : index + 1]
        atr = compute_atr([candles[index - period]] + window, period)
        result.append({"time": candle_time(candles[index]), "value": atr})

    return result
