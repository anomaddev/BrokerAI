from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from brokerai.bots.data_manager.candle_schedule import timeframe_to_duration
from brokerai.trading.data.time_utils import format_oanda_time, parse_oanda_time

ET = ZoneInfo("America/New_York")

# Spot FX daily maintenance window (America/New_York).
_DAILY_BREAK_START = time(17, 0)
_DAILY_BREAK_END = time(18, 0)
_WEEK_OPEN = time(17, 0)  # Sunday open


def _to_et(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).astimezone(ET)
    return value.astimezone(ET)


def is_forex_open(when: datetime) -> bool:
    """Return True when the spot FX market is open at *when* (America/New_York rules).

    Closed on Saturdays, before Sunday 17:00 ET, during the weekday 17:00–18:00 ET
    break, and from Friday 17:00 ET through Sunday open.
    """
    et = _to_et(when)
    weekday = et.weekday()  # Mon=0 … Sun=6

    if weekday == 5:
        return False

    if weekday == 6:
        return et.time() >= _WEEK_OPEN

    if weekday == 4 and et.time() >= _DAILY_BREAK_START:
        return False

    if _DAILY_BREAK_START <= et.time() < _DAILY_BREAK_END:
        return False

    return True


def _align_bar_open(value: datetime, timeframe: str) -> datetime:
    """Return the UTC open time of the bar containing *value*."""
    if value.tzinfo is None:
        when = value.replace(tzinfo=timezone.utc)
    else:
        when = value.astimezone(timezone.utc)

    if timeframe == "MN":
        return when.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    duration = timeframe_to_duration(timeframe)
    period_seconds = int(duration.total_seconds())
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    elapsed = int((when - epoch).total_seconds())
    aligned = elapsed - (elapsed % period_seconds)
    return epoch + timedelta(seconds=aligned)


def _next_bar_open(bar_open: datetime, timeframe: str) -> datetime:
    if timeframe == "MN":
        if bar_open.month == 12:
            return bar_open.replace(year=bar_open.year + 1, month=1, day=1)
        return bar_open.replace(month=bar_open.month + 1, day=1)
    duration = timeframe_to_duration(timeframe)
    return bar_open + duration


def iter_expected_bar_times(
    start: datetime,
    end: datetime,
    timeframe: str,
) -> list[datetime]:
    """Yield bar open times between *start* and *end* during open forex hours."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    else:
        start = start.astimezone(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    else:
        end = end.astimezone(timezone.utc)

    if start > end:
        return []

    current = _align_bar_open(start, timeframe)
    if current < start:
        current = _next_bar_open(current, timeframe)

    bars: list[datetime] = []
    while current <= end:
        if is_forex_open(current):
            bars.append(current)
        current = _next_bar_open(current, timeframe)
    return bars


def missing_times_in_range(
    stored_times: set[str],
    start: datetime,
    end: datetime,
    timeframe: str,
) -> list[str]:
    """Return OANDA-formatted open times expected in range but absent from *stored_times*."""
    expected = iter_expected_bar_times(start, end, timeframe)
    missing: list[str] = []
    for bar_open in expected:
        key = format_oanda_time(bar_open)
        if key not in stored_times:
            missing.append(key)
    return missing


def _previous_bar_open(bar_open: datetime, timeframe: str) -> datetime:
    if timeframe == "MN":
        if bar_open.month == 1:
            return bar_open.replace(year=bar_open.year - 1, month=12, day=1)
        return bar_open.replace(month=bar_open.month - 1, day=1)
    return bar_open - timeframe_to_duration(timeframe)


def expected_latest_closed_bar(
    timeframe: str,
    *,
    as_of: datetime | None = None,
) -> datetime | None:
    """Return the open time of the latest fully closed bar before *as_of* (UTC)."""
    if as_of is None:
        when = datetime.now(timezone.utc)
    elif as_of.tzinfo is None:
        when = as_of.replace(tzinfo=timezone.utc)
    else:
        when = as_of.astimezone(timezone.utc)

    current_open = _align_bar_open(when, timeframe)
    candidate = _previous_bar_open(current_open, timeframe)

    for _ in range(500):
        if is_forex_open(candidate):
            return candidate
        candidate = _previous_bar_open(candidate, timeframe)

    return None


def latest_closed_bar_time_string(
    timeframe: str,
    *,
    as_of: datetime | None = None,
) -> str | None:
    """Return OANDA-formatted open time for ``expected_latest_closed_bar``."""
    latest = expected_latest_closed_bar(timeframe, as_of=as_of)
    if latest is None:
        return None
    return format_oanda_time(latest)


def stored_time_matches_expected(latest_stored: str, expected: datetime) -> bool:
    """Compare stored OANDA time string to an expected bar open datetime."""
    try:
        parsed = parse_oanda_time(latest_stored)
    except ValueError:
        return False
    return abs((parsed - expected).total_seconds()) < 1.0
