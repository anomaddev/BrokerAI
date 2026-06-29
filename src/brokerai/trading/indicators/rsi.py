from __future__ import annotations

from typing import Any

from brokerai.trading.indicators._candles import candle_close, candle_time


def compute_rsi(candles: list[dict[str, Any]], period: int) -> list[dict[str, Any]]:
    if len(candles) < period + 1:
        return []

    result: list[dict[str, Any]] = []
    gains = 0.0
    losses = 0.0

    for index in range(1, period + 1):
        change = candle_close(candles[index]) - candle_close(candles[index - 1])
        if change >= 0:
            gains += change
        else:
            losses -= change

    avg_gain = gains / period
    avg_loss = losses / period

    for index in range(period, len(candles)):
        if index > period:
            change = candle_close(candles[index]) - candle_close(candles[index - 1])
            gain = max(change, 0.0)
            loss = max(-change, 0.0)
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        result.append({"time": candle_time(candles[index]), "value": rsi})

    return result
