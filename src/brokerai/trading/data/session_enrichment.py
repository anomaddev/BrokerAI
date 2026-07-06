from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from brokerai.market_sessions import TRADING_SESSIONS, is_session_active

UTC = timezone.utc
NY = ZoneInfo("America/New_York")

# Overlap windows in America/New_York wall clock.
_ASIA_LONDON_OVERLAP_START = time(3, 0)
_ASIA_LONDON_OVERLAP_END = time(5, 0)
_LONDON_NY_OVERLAP_START = time(8, 0)
_LONDON_NY_OVERLAP_END = time(12, 0)

_SESSION_BY_ID = {session.id: session for session in TRADING_SESSIONS}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _et_clock(when: datetime) -> time:
    return when.astimezone(NY).time()


def sessions_for_bar(bar_open: datetime) -> list[str]:
    """Tag a bar open time with active FX liquidity session labels."""
    when = _as_utc(bar_open)
    sessions: list[str] = []

    for session in TRADING_SESSIONS:
        if is_session_active(session, when):
            sessions.append(session.id)

    clock = _et_clock(when)
    if (
        _ASIA_LONDON_OVERLAP_START <= clock < _ASIA_LONDON_OVERLAP_END
        and "asia" in sessions
        and "london" in sessions
    ):
        sessions.append("asia_london_overlap")
    if (
        _LONDON_NY_OVERLAP_START <= clock < _LONDON_NY_OVERLAP_END
        and "london" in sessions
        and "ny" in sessions
    ):
        sessions.append("london_ny_overlap")

    return sessions


def trading_day_et(bar_open: datetime) -> str:
    """Return the America/New_York calendar date for *bar_open*."""
    when = _as_utc(bar_open)
    return when.astimezone(NY).date().isoformat()


def enrich_candle(candle: dict) -> dict:
    """Attach session tags and ET trading day to a normalized candle dict."""
    time_raw = candle.get("time")
    if not time_raw:
        return candle

    from brokerai.trading.data.time_utils import parse_oanda_time

    try:
        opened = parse_oanda_time(str(time_raw))
    except ValueError:
        return candle

    enriched = dict(candle)
    sessions = sessions_for_bar(opened)
    if sessions:
        enriched["sessions"] = sessions
    enriched["trading_day_et"] = trading_day_et(opened)
    return enriched


def enrich_candles(candles: list[dict]) -> list[dict]:
    """Enrich a batch of candles with session metadata."""
    return [enrich_candle(candle) for candle in candles]
