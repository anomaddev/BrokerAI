from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from brokerai.trading.data.market_calendar import (
    expected_latest_closed_bar,
    is_forex_open,
    iter_expected_bar_times,
    missing_times_in_range,
)
from brokerai.trading.data.session_enrichment import sessions_for_bar
from brokerai.trading.data.time_utils import format_oanda_time

ET = ZoneInfo("America/New_York")


def test_forex_closed_on_saturday():
    when = datetime(2026, 1, 3, 12, 0, tzinfo=ET)
    assert is_forex_open(when) is False


def test_forex_open_midweek():
    when = datetime(2026, 1, 7, 10, 0, tzinfo=ET)
    assert is_forex_open(when) is True


def test_forex_daily_break():
    when = datetime(2026, 1, 7, 17, 0, tzinfo=ET)
    assert is_forex_open(when) is False


def test_expected_bars_skip_weekend():
    start = datetime(2026, 1, 9, 14, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 9, 20, 0, tzinfo=timezone.utc)
    bars = list(iter_expected_bar_times(start, end, "H1"))
    assert len(bars) >= 4
    for bar in bars:
        assert is_forex_open(bar)


def test_missing_times_detects_gap():
    start = datetime(2026, 1, 7, 13, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 7, 15, 0, tzinfo=timezone.utc)
    expected = list(iter_expected_bar_times(start, end, "H1"))
    stored = {format_oanda_time(expected[0])}
    missing = missing_times_in_range(stored, start, end, "H1")
    assert len(missing) == len(expected) - 1


def test_london_ny_overlap_tagged():
    when = datetime(2026, 1, 7, 15, 0, tzinfo=timezone.utc)
    sessions = sessions_for_bar(when)
    assert "london" in sessions
    assert "ny" in sessions
    assert "london_ny_overlap" in sessions


def test_asia_london_overlap_tagged():
    when = datetime(2026, 1, 7, 8, 30, tzinfo=timezone.utc)  # 3:30 AM ET
    sessions = sessions_for_bar(when)
    assert "asia" in sessions
    assert "london" in sessions
    assert "asia_london_overlap" in sessions


def test_asia_session_tagged_outside_london():
    when = datetime(2026, 1, 7, 6, 0, tzinfo=timezone.utc)  # 1:00 AM ET
    sessions = sessions_for_bar(when)
    assert "asia" in sessions
    assert "london" not in sessions


def test_sydney_session_tagged_evening_et():
    when = datetime(2026, 1, 7, 23, 0, tzinfo=timezone.utc)  # 6:00 PM ET
    sessions = sessions_for_bar(when)
    assert "sydney" in sessions


def test_expected_latest_closed_bar_during_open_market():
    as_of = datetime(2026, 1, 7, 15, 30, tzinfo=timezone.utc)
    latest = expected_latest_closed_bar("M15", as_of=as_of)
    assert latest is not None
    assert latest < as_of
