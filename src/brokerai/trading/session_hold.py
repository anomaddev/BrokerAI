"""Session-island and major-market-close helpers for hold / late-entry rules.

Hierarchy (same pattern as Forex asset/pair enablement):
1. Globally enabled on the asset (``enabled_sessions`` / asset ``enabled`` + pairs)
2. Enabled on the strategy (``execution.sessions`` / instrument selection)

Effective sessions are the intersection of those two layers. Major market closes
are weekend (and future holiday) boundaries only — not the Mon–Thu FX daily break.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from brokerai.bots.data_manager.candle_schedule import timeframe_to_duration
from brokerai.market_sessions import (
    TRADING_SESSIONS,
    current_session_close,
    is_forex_hours,
    is_session_active,
    normalize_enabled_sessions,
)
from brokerai.trading.data.market_calendar import ET, align_bar_open, is_forex_open
from brokerai.trading.session_gate import normalize_strategy_sessions

_SESSION_BY_ID = {session.id: session for session in TRADING_SESSIONS}
_DEFAULT_CLOSE_BEFORE_HOURS = 2
_DEFAULT_LATE_MARKET_HOURS = 2
_FX_WEEK_CLOSE = (17, 0)  # Friday 17:00 America/New_York


def effective_session_ids(
    asset_enabled: dict[str, bool] | None,
    strategy_params: dict[str, Any],
) -> set[str]:
    """Return session ids enabled both globally and on the strategy."""
    asset = normalize_enabled_sessions(asset_enabled)
    execution = strategy_params.get("execution") or {}
    strategy_ids = normalize_strategy_sessions(list(execution.get("sessions") or []))
    if not strategy_ids:
        # Empty strategy list means "all sessions" for entry gates; for hold
        # logic treat as all globally enabled sessions.
        return {sid for sid, on in asset.items() if on}
    return {sid for sid in strategy_ids if asset.get(sid, False)}


def is_effective_session_coverage(
    when: datetime,
    effective_ids: set[str] | frozenset[str],
) -> bool:
    """True when FX is open and at least one effective session is active."""
    if not effective_ids:
        return False
    if not is_forex_hours(when):
        return False
    for session_id in effective_ids:
        session = _SESSION_BY_ID.get(session_id)
        if session and is_session_active(session, when):
            return True
    return False


def next_coverage_end(
    when: datetime,
    effective_ids: set[str] | frozenset[str],
) -> datetime | None:
    """Return when the current effective-session coverage island ends.

    With overlapping sessions, coverage continues until the latest close among
    currently active effective sessions, extended by any other effective session
    that is already open or opens before that close and itself ends later.
    """
    if not is_effective_session_coverage(when, effective_ids):
        return None

    # Expand the island by repeatedly taking the max close of sessions that
    # overlap the growing window.
    island_end: datetime | None = None
    cursor = when
    for _ in range(16):
        active_closes: list[datetime] = []
        for session_id in effective_ids:
            session = _SESSION_BY_ID.get(session_id)
            if session is None:
                continue
            if not is_session_active(session, cursor):
                continue
            close_at = current_session_close(session, cursor)
            if close_at is not None:
                active_closes.append(close_at)
        if not active_closes:
            break
        candidate = max(active_closes)
        if island_end is not None and candidate <= island_end:
            break
        island_end = candidate
        # Peek just before the candidate close for an overlapping session that
        # extends further; step to mid-island to continue expansion.
        cursor = candidate - timedelta(seconds=1)
        if not is_effective_session_coverage(cursor, effective_ids):
            break
    return island_end


def _next_bar_open(bar_open: datetime, timeframe: str) -> datetime:
    if timeframe == "MN":
        if bar_open.month == 12:
            return bar_open.replace(year=bar_open.year + 1, month=1, day=1)
        return bar_open.replace(month=bar_open.month + 1, day=1)
    return bar_open + timeframe_to_duration(timeframe)


def would_leave_coverage_on_next_candle(
    when: datetime,
    timeframe: str,
    effective_ids: set[str] | frozenset[str],
) -> bool:
    """True when *when*'s bar is the last in-coverage bar before a gap.

    Edge cases:
    - Already outside coverage → False (nothing to leave).
    - Next bar still covered (overlap / continuous sessions) → False.
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)

    bar_open = align_bar_open(when, timeframe)
    if not is_effective_session_coverage(bar_open, effective_ids):
        # Also accept evaluation at bar close / mid-bar if the open was covered.
        if not is_effective_session_coverage(when, effective_ids):
            return False
        bar_open = align_bar_open(when, timeframe)

    next_open = _next_bar_open(bar_open, timeframe)
    # Skip bars that fall in FX-closed periods so "next candle" matches trading bars.
    for _ in range(500):
        if is_forex_open(next_open):
            break
        next_open = _next_bar_open(next_open, timeframe)

    in_now = is_effective_session_coverage(when, effective_ids) or is_effective_session_coverage(
        bar_open, effective_ids
    )
    in_next = is_effective_session_coverage(next_open, effective_ids)
    return in_now and not in_next


def _friday_on_or_after(day: date) -> date:
    # Monday=0 … Sunday=6; Friday=4
    offset = (4 - day.weekday()) % 7
    return day + timedelta(days=offset)


def _session_close_on_local_date(session_id: str, local_day: date) -> datetime | None:
    """Return the session's end datetime for a given local calendar day."""
    session = _SESSION_BY_ID.get(session_id)
    if session is None:
        return None
    tz = ZoneInfo(session.timezone)
    start = session.start_hour * 60 + session.start_minute
    end = session.end_hour * 60 + session.end_minute
    if start <= end:
        close_local = datetime(
            local_day.year,
            local_day.month,
            local_day.day,
            session.end_hour,
            session.end_minute,
            tzinfo=tz,
        )
    else:
        # Overnight: ends on local_day at end_hour (started previous evening).
        close_local = datetime(
            local_day.year,
            local_day.month,
            local_day.day,
            session.end_hour,
            session.end_minute,
            tzinfo=tz,
        )
    return close_local.astimezone(timezone.utc)


def _friday_et_week_close(friday: date) -> datetime:
    hour, minute = _FX_WEEK_CLOSE
    return datetime(friday.year, friday.month, friday.day, hour, minute, tzinfo=ET).astimezone(
        timezone.utc
    )


def next_major_market_close(
    when: datetime,
    effective_ids: set[str] | frozenset[str],
) -> datetime | None:
    """Next weekend major close for the effective session set.

    Uses the latest effective-session end on the upcoming Friday that is still
    at or before the FX week close (Friday 17:00 ET). Daily Mon–Thu breaks are
    not major closes. Returns ``None`` when *effective_ids* is empty.
    """
    if not effective_ids:
        return None

    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)

    when_et = when.astimezone(ET)
    friday = _friday_on_or_after(when_et.date())

    for _ in range(3):
        week_close = _friday_et_week_close(friday)
        candidates: list[datetime] = []
        for session_id in effective_ids:
            session = _SESSION_BY_ID.get(session_id)
            if session is None:
                continue
            # Evaluate close on Friday in the session's timezone calendar day that
            # corresponds to the ET Friday trading day.
            if session.timezone == "America/New_York":
                close_at = _session_close_on_local_date(session_id, friday)
            else:
                # Map ET Friday noon as anchor → session-local date for close lookup.
                anchor = datetime(friday.year, friday.month, friday.day, 12, 0, tzinfo=ET)
                local_day = anchor.astimezone(ZoneInfo(session.timezone)).date()
                close_at = _session_close_on_local_date(session_id, local_day)
            if close_at is None:
                continue
            # Overnight sessions may end early Friday (e.g. Sydney 02:00 ET).
            if close_at <= week_close:
                candidates.append(close_at)

        major = max(candidates) if candidates else week_close
        if when < major:
            return major
        friday = friday + timedelta(days=7)

    return None


def hours_until_major_market_close(
    when: datetime,
    effective_ids: set[str] | frozenset[str],
) -> float | None:
    close_at = next_major_market_close(when, effective_ids)
    if close_at is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)
    return (close_at - when).total_seconds() / 3600.0


def is_within_major_market_close_window(
    when: datetime,
    hours: int,
    effective_ids: set[str] | frozenset[str],
) -> bool:
    """True when *when* is within *hours* of the next major market close."""
    if hours <= 0:
        return False
    remaining = hours_until_major_market_close(when, effective_ids)
    if remaining is None:
        return False
    return 0 <= remaining <= float(hours)


def should_force_close_session_boundary(
    params: dict[str, Any],
    *,
    when: datetime,
    timeframe: str,
    asset_enabled_sessions: dict[str, bool] | None,
) -> bool:
    execution = params.get("execution") or {}
    if not bool(execution.get("dont_hold_between_sessions", True)):
        return False
    effective = effective_session_ids(asset_enabled_sessions, params)
    return would_leave_coverage_on_next_candle(when, timeframe, effective)


def should_force_close_market(
    params: dict[str, Any],
    *,
    when: datetime,
    asset_enabled_sessions: dict[str, bool] | None,
) -> bool:
    execution = params.get("execution") or {}
    if not bool(execution.get("dont_hold_between_markets", True)):
        return False
    hours = int(execution.get("close_before_market_hours", _DEFAULT_CLOSE_BEFORE_HOURS))
    effective = effective_session_ids(asset_enabled_sessions, params)
    return is_within_major_market_close_window(when, hours, effective)


def should_block_late_market_entry(
    params: dict[str, Any],
    *,
    when: datetime,
    asset_enabled_sessions: dict[str, bool] | None,
) -> tuple[bool, dict[str, Any]]:
    """Return (blocked, details) for the late-market entry gate."""
    execution = params.get("execution") or {}
    if not bool(execution.get("no_late_market_trading", True)):
        return False, {}
    hours = int(execution.get("late_market_hours", _DEFAULT_LATE_MARKET_HOURS))
    effective = effective_session_ids(asset_enabled_sessions, params)
    remaining = hours_until_major_market_close(when, effective)
    if remaining is None:
        return False, {}
    if 0 <= remaining <= float(hours):
        return True, {
            "hours_until_close": round(remaining, 4),
            "late_market_hours": hours,
            "effective_sessions": sorted(effective),
        }
    return False, {}
