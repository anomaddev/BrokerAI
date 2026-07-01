from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
LONDON = ZoneInfo("Europe/London")
NY = ZoneInfo("America/New_York")

# Approximate liquid session windows in UTC (bar open time).
_LONDON_START = time(8, 0)
_LONDON_END = time(17, 0)
_NY_START = time(13, 0)
_NY_END = time(22, 0)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def sessions_for_bar(bar_open: datetime) -> list[str]:
    """Tag a bar open time with active FX session labels (UTC-based windows)."""
    when = _as_utc(bar_open)
    clock = when.time()
    sessions: list[str] = []

    if _LONDON_START <= clock < _LONDON_END:
        sessions.append("london")
    if _NY_START <= clock < _NY_END:
        sessions.append("ny")
    if "london" in sessions and "ny" in sessions:
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
