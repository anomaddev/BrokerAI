"""Resolve backtest period presets to UTC windows (America/New_York aware)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from brokerai.db.repositories.backtest_runs import BACKTEST_PERIODS, normalize_backtest_period

NY = ZoneInfo("America/New_York")

_PERIOD_DELTAS: dict[str, timedelta] = {
    "1m": timedelta(days=30),
    "3m": timedelta(days=90),
    "6m": timedelta(days=182),
    "1y": timedelta(days=365),
    "2y": timedelta(days=730),
    "5y": timedelta(days=1825),
}


def resolve_period_window(
    period: str,
    *,
    end: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return ``(start_utc, end_utc)`` for a period preset ending at *end* (default now).

    The end instant is snapped to the current moment in America/New_York so
    weekend/holiday boundaries stay consistent with market-session helpers.
    Start is ``end - period_delta``.

    Edge cases:
    - Unknown period falls back to ``6m``.
    - Naive *end* is treated as UTC.
    """
    key = normalize_backtest_period(period)
    if key not in BACKTEST_PERIODS:
        key = "6m"
    end_utc = end or datetime.now(timezone.utc)
    if end_utc.tzinfo is None:
        end_utc = end_utc.replace(tzinfo=timezone.utc)
    else:
        end_utc = end_utc.astimezone(timezone.utc)

    end_ny = end_utc.astimezone(NY)
    start_ny = end_ny - _PERIOD_DELTAS[key]
    return start_ny.astimezone(timezone.utc), end_utc


def format_oanda_bound(when: datetime) -> str:
    """Format a datetime as an OANDA/RFC3339 UTC timestamp string."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)
    return when.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
