from __future__ import annotations

from datetime import datetime, timezone

from brokerai.bots.data_manager.candle_schedule import is_candle_fetch_due, next_candle_close_at


def next_analysis_at(now: datetime, timeframe: str) -> datetime:
    """Return when the next closed-candle analysis should run for a timeframe."""
    return next_candle_close_at(now, timeframe)


def is_analysis_due(now: datetime, next_at: datetime | None) -> bool:
    """True when analysis should run for a timeframe."""
    return is_candle_fetch_due(now, next_at)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
