from __future__ import annotations

from datetime import datetime, timedelta, timezone

from brokerai.strategies.params.constants import TIMEFRAMES

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
# Small buffer after the boundary so OANDA marks the prior bar complete.
CLOSE_BUFFER = timedelta(seconds=3)


def timeframe_to_duration(timeframe: str) -> timedelta:
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    if timeframe == "MN":
        return timedelta(days=30)

    if timeframe.startswith("M") and timeframe[1:].isdigit():
        return timedelta(minutes=int(timeframe[1:]))

    if timeframe.startswith("H") and timeframe[1:].isdigit():
        return timedelta(hours=int(timeframe[1:]))

    if timeframe == "D1":
        return timedelta(days=1)
    if timeframe == "W1":
        return timedelta(weeks=1)

    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month_start(value: datetime) -> datetime:
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return value.replace(month=value.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def next_candle_close_at(
    now: datetime,
    timeframe: str,
    *,
    buffer: timedelta = CLOSE_BUFFER,
) -> datetime:
    """Return when the currently forming candle closes (+ buffer), UTC."""
    if now.tzinfo is None:
        when = now.replace(tzinfo=timezone.utc)
    else:
        when = now.astimezone(timezone.utc)

    if timeframe == "MN":
        month_start = _month_start(when)
        if when == month_start:
            close_at = _next_month_start(when)
        elif when > month_start:
            close_at = _next_month_start(month_start)
        else:
            close_at = month_start
        return close_at + buffer

    duration = timeframe_to_duration(timeframe)
    period_seconds = int(duration.total_seconds())
    elapsed = int((when - _EPOCH).total_seconds())
    next_boundary = _EPOCH + timedelta(seconds=((elapsed // period_seconds) + 1) * period_seconds)
    return next_boundary + buffer


def is_candle_fetch_due(
    now: datetime,
    next_fetch_at: datetime | None,
) -> bool:
    if next_fetch_at is None:
        return False
    if now.tzinfo is None:
        when = now.replace(tzinfo=timezone.utc)
    else:
        when = now.astimezone(timezone.utc)
    return when >= next_fetch_at.astimezone(timezone.utc)
