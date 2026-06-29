from __future__ import annotations

from typing import Any


def candle_time(candle: dict[str, Any]) -> str:
    return str(candle.get("time", ""))


def candle_close(candle: dict[str, Any]) -> float:
    return float(candle["close"])


def candle_source_value(candle: dict[str, Any], source: str) -> float:
    if source == "open":
        return float(candle["open"])
    if source == "high":
        return float(candle["high"])
    if source == "low":
        return float(candle["low"])
    if source == "hl2":
        return (float(candle["high"]) + float(candle["low"])) / 2
    if source == "hlc3":
        return (float(candle["high"]) + float(candle["low"]) + float(candle["close"])) / 3
    if source == "ohlc4":
        return (
            float(candle["open"])
            + float(candle["high"])
            + float(candle["low"])
            + float(candle["close"])
        ) / 4
    return float(candle["close"])
