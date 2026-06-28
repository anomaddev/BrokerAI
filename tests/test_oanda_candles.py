from __future__ import annotations

from brokerai.integrations.oanda import (
    _oanda_request_count,
    _parse_oanda_candles,
    _trim_closed_candles,
    normalize_oanda_candle,
)


def _raw_candle(*, complete: bool, time: str = "2026-01-01T00:00:00.000000000Z") -> dict:
    return {
        "time": time,
        "complete": complete,
        "volume": 10,
        "mid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.15"},
    }


def test_normalize_oanda_candle_requires_complete_true():
    assert normalize_oanda_candle(_raw_candle(complete=True)) is not None
    assert normalize_oanda_candle(_raw_candle(complete=False)) is None
    assert normalize_oanda_candle({"time": "t", "mid": {"o": "1", "h": "1", "l": "1", "c": "1"}}) is None


def test_parse_oanda_candles_skips_incomplete():
    payload = {
        "candles": [
            _raw_candle(complete=True, time="2026-01-01T00:00:00.000000000Z"),
            _raw_candle(complete=False, time="2026-01-01T00:15:00.000000000Z"),
        ]
    }
    parsed = _parse_oanda_candles(payload)
    assert len(parsed) == 1
    assert parsed[0]["time"] == "2026-01-01T00:00:00.000000000Z"


def test_oanda_request_count_requests_one_extra_bar():
    assert _oanda_request_count(63) == 64
    assert _oanda_request_count(5000) == 5000


def test_trim_closed_candles_keeps_most_recent_closed_bars():
    candles = [
        {"time": "1", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0},
        {"time": "2", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0},
        {"time": "3", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0},
    ]
    assert _trim_closed_candles(candles, 2) == candles[-2:]
