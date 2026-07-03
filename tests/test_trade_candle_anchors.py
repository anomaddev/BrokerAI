from __future__ import annotations

from datetime import datetime, timezone

from brokerai.db.repositories.broker_lots import fill_candle_anchors
from brokerai.trading.data.market_calendar import bar_open_for_instant, bar_open_string_for_instant


def test_bar_open_m15_floors_to_bar_start():
    # OANDA trade 553 opened at 07:32:14 UTC → M15 bar opens at 07:30:00
    instant = datetime(2026, 7, 1, 7, 32, 14, 821946, tzinfo=timezone.utc)
    aligned = bar_open_for_instant(instant, "M15")
    assert aligned == datetime(2026, 7, 1, 7, 30, tzinfo=timezone.utc)


def test_bar_open_m15_exit_bar():
    instant = datetime(2026, 7, 1, 7, 57, 16, 870490, tzinfo=timezone.utc)
    aligned = bar_open_for_instant(instant, "M15")
    assert aligned == datetime(2026, 7, 1, 7, 45, tzinfo=timezone.utc)


def test_bar_open_string_from_oanda_iso():
    open_time = "2026-07-01T07:32:14.821946294Z"
    result = bar_open_string_for_instant(open_time, "M15")
    assert result is not None
    assert result.startswith("2026-07-01T07:30:00")


def test_bar_open_h1():
    instant = datetime(2026, 7, 1, 10, 58, 5, tzinfo=timezone.utc)
    aligned = bar_open_for_instant(instant, "H1")
    assert aligned == datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)


def test_fill_candle_anchors_derives_missing_fields():
    doc = {
        "state": "closed",
        "open_time": datetime(2026, 7, 1, 7, 32, 14, tzinfo=timezone.utc),
        "close_time": datetime(2026, 7, 1, 7, 57, 16, tzinfo=timezone.utc),
    }
    filled = fill_candle_anchors(doc, strategy_timeframe="M15")
    assert filled["timeframe"] == "M15"
    assert filled["entry_candle_open"].startswith("2026-07-01T07:30:00")
    assert filled["exit_candle_open"].startswith("2026-07-01T07:45:00")


def test_fill_candle_anchors_does_not_overwrite_existing():
    doc = {
        "state": "closed",
        "timeframe": "M15",
        "entry_candle_open": "2026-07-01T07:15:00.000000000Z",
        "exit_candle_open": "2026-07-01T07:45:00.000000000Z",
        "open_time": datetime(2026, 7, 1, 7, 32, 14, tzinfo=timezone.utc),
        "close_time": datetime(2026, 7, 1, 7, 57, 16, tzinfo=timezone.utc),
    }
    filled = fill_candle_anchors(doc, strategy_timeframe="H1")
    assert filled["timeframe"] == "M15"
    assert filled["entry_candle_open"] == "2026-07-01T07:15:00.000000000Z"
    assert filled["exit_candle_open"] == "2026-07-01T07:45:00.000000000Z"
