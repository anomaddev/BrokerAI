from __future__ import annotations

from datetime import datetime, timezone

from brokerai.bots.data_manager.candle_schedule import (
    CLOSE_BUFFER,
    is_candle_fetch_due,
    next_candle_close_at,
    timeframe_to_duration,
)


def test_timeframe_to_duration_m15():
    assert timeframe_to_duration("M15").total_seconds() == 15 * 60


def test_timeframe_to_duration_h1():
    assert timeframe_to_duration("H1").total_seconds() == 3600


def test_next_candle_close_at_m15_mid_period():
    now = datetime(2026, 6, 28, 12, 7, 30, tzinfo=timezone.utc)
    close_at = next_candle_close_at(now, "M15")
    assert close_at == datetime(2026, 6, 28, 12, 15, 3, tzinfo=timezone.utc)


def test_next_candle_close_at_m15_on_boundary():
    now = datetime(2026, 6, 28, 12, 15, 0, tzinfo=timezone.utc)
    close_at = next_candle_close_at(now, "M15")
    assert close_at == datetime(2026, 6, 28, 12, 30, 3, tzinfo=timezone.utc)


def test_is_candle_fetch_due():
    now = datetime(2026, 6, 28, 12, 16, 0, tzinfo=timezone.utc)
    due_at = datetime(2026, 6, 28, 12, 15, 3, tzinfo=timezone.utc)
    assert is_candle_fetch_due(now, due_at) is True
    assert is_candle_fetch_due(now, None) is False


def test_next_candle_close_includes_buffer():
    now = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)
    close_at = next_candle_close_at(now, "M15", buffer=CLOSE_BUFFER)
    assert (close_at - datetime(2026, 6, 28, 12, 15, 0, tzinfo=timezone.utc)) == CLOSE_BUFFER
