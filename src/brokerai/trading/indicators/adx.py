from __future__ import annotations

from typing import Any

from brokerai.trading.indicators._candles import candle_close, candle_time


def compute_adx(candles: list[dict[str, Any]], period: int) -> list[dict[str, Any]]:
    if len(candles) < period + 2:
        return []

    result: list[dict[str, Any]] = []
    prev_high = float(candles[0]["high"])
    prev_low = float(candles[0]["low"])
    prev_close = candle_close(candles[0])
    tr_sm = 0.0
    plus_dm_sm = 0.0
    minus_dm_sm = 0.0
    adx_sm = 0.0

    for index in range(1, len(candles)):
        high = float(candles[index]["high"])
        low = float(candles[index]["low"])
        close = candle_close(candles[index])
        up_move = high - prev_high
        down_move = prev_low - low
        plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0
        true_range = max(high - low, abs(high - prev_close), abs(low - prev_close))

        if index <= period:
            tr_sm += true_range
            plus_dm_sm += plus_dm
            minus_dm_sm += minus_dm
        else:
            tr_sm = tr_sm - tr_sm / period + true_range
            plus_dm_sm = plus_dm_sm - plus_dm_sm / period + plus_dm
            minus_dm_sm = minus_dm_sm - minus_dm_sm / period + minus_dm

        if index >= period:
            plus_di = 0.0 if tr_sm == 0 else (100 * plus_dm_sm) / tr_sm
            minus_di = 0.0 if tr_sm == 0 else (100 * minus_dm_sm) / tr_sm
            di_sum = plus_di + minus_di
            dx = 0.0 if di_sum == 0 else (100 * abs(plus_di - minus_di)) / di_sum
            adx_sm = dx if index == period else (adx_sm * (period - 1) + dx) / period
            result.append({"time": candle_time(candles[index]), "value": min(60.0, adx_sm)})

        prev_high = high
        prev_low = low
        prev_close = close

    return result
