from __future__ import annotations

import math


def pseudo_random(seed: int) -> float:
    x = math.sin(seed * 12.9898 + seed * 78.233) * 43758.5453
    return x - math.floor(x)


def generate_mock_candles(count: int = 120) -> list[dict]:
    candles: list[dict] = []
    price = 1.085
    start = 1_700_000_000 - count * 900

    for index in range(count):
        drift = math.sin(index / 8) * 0.0004 + (pseudo_random(index) - 0.5) * 0.0012
        open_price = price
        close = open_price + drift
        wick = 0.0003 + pseudo_random(index + 100) * 0.0008
        high = max(open_price, close) + wick
        low = min(open_price, close) - wick
        candles.append(
            {
                "time": str(start + index * 900),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
            }
        )
        price = close

    return candles
