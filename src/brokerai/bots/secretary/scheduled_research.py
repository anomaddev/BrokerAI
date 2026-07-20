"""Deferral helpers so secretary does not re-probe research schedules every tick."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from brokerai.research_markets import (
    next_weekly_brief_run_utc,
    next_weekly_debrief_run_utc,
    scheduled_run_utc,
)

# Stable config/skip reasons: wait for settings change (fingerprint invalidates).
_STABLE_UNTIL_SETTINGS = datetime(9999, 1, 1, tzinfo=timezone.utc)

# Waiting on report inputs that may appear later (manual backfill, late daily).
_WAITING_INPUTS = timedelta(minutes=30)

# After launching a job, avoid double-dispatch while it starts.
_AFTER_LAUNCH = timedelta(seconds=60)

_FINGERPRINT_KEYS = (
    "daily_report_enabled",
    "daily_report_market_id",
    "daily_report_market_offset_hours",
    "last_daily_run_date",
    "weekly_brief_enabled",
    "weekly_brief_model_id",
    "weekly_brief_market_id",
    "weekly_brief_market_offset_hours",
    "last_weekly_brief_run_week",
    "weekly_debrief_enabled",
    "weekly_debrief_model_id",
    "weekly_debrief_market_id",
    "weekly_debrief_market_offset_hours",
    "last_weekly_debrief_run_week",
)


def research_settings_fingerprint(settings: dict[str, Any]) -> str:
    """Compact snapshot of fields that affect scheduled research probes."""
    return "|".join(f"{key}={settings.get(key)!r}" for key in _FINGERPRINT_KEYS)


def after_launch_deferral(now: datetime) -> datetime:
    return now + _AFTER_LAUNCH


def next_daily_probe_at(now: datetime, settings: dict[str, Any], *, done_today: bool) -> datetime:
    """When to next evaluate the daily report schedule."""
    market_id = settings.get("daily_report_market_id", "london")
    offset = settings.get("daily_report_market_offset_hours", -2)
    scheduled = scheduled_run_utc(market_id, offset, now=now)
    if not done_today and now < scheduled:
        return scheduled
    # Done for today, or past today's slot without completion — try tomorrow's slot.
    tomorrow: date = now.date() + timedelta(days=1)
    return scheduled_run_utc(market_id, offset, on=tomorrow)


def next_brief_probe_at(now: datetime, settings: dict[str, Any], skip: str | None) -> datetime:
    """When to next evaluate weekly brief after a probe outcome."""
    if skip is None:
        return after_launch_deferral(now)
    return _next_weekly_probe_at(
        skip,
        now,
        market_id=settings.get("weekly_brief_market_id", "london"),
        offset=settings.get("weekly_brief_market_offset_hours", -1),
        next_slot=next_weekly_brief_run_utc,
        already_markers=("already ran", "already exists"),
    )


def next_debrief_probe_at(now: datetime, settings: dict[str, Any], skip: str | None) -> datetime:
    """When to next evaluate weekly debrief after a probe outcome."""
    if skip is None:
        return after_launch_deferral(now)
    return _next_weekly_probe_at(
        skip,
        now,
        market_id=settings.get("weekly_debrief_market_id", "london"),
        offset=settings.get("weekly_debrief_market_offset_hours", 1),
        next_slot=next_weekly_debrief_run_utc,
        already_markers=("already ran", "already exists"),
    )


def next_debrief_schedule_probe_at(now: datetime, settings: dict[str, Any]) -> datetime:
    """Defer until the next Friday-close debrief slot when none is due yet."""
    return next_weekly_debrief_run_utc(
        settings.get("weekly_debrief_market_id", "london"),
        settings.get("weekly_debrief_market_offset_hours", 1),
        now=now,
    )


def next_brief_schedule_probe_at(now: datetime, settings: dict[str, Any]) -> datetime:
    """Defer until the next Monday-open brief slot when none is due yet."""
    return next_weekly_brief_run_utc(
        settings.get("weekly_brief_market_id", "london"),
        settings.get("weekly_brief_market_offset_hours", -1),
        now=now,
    )


def _next_weekly_probe_at(
    skip: str,
    now: datetime,
    *,
    market_id: str,
    offset: int,
    next_slot: Callable[..., datetime],
    already_markers: tuple[str, ...],
) -> datetime:
    lower = skip.lower()
    if any(marker in lower for marker in already_markers):
        return next_slot(market_id, offset, now=now)
    if _is_stable_config_skip(lower):
        return _STABLE_UNTIL_SETTINGS
    if "insufficient" in lower or "not ready" in lower or "missing" in lower:
        return now + _WAITING_INPUTS
    if "schedule has not passed" in lower or "disabled" in lower:
        return _STABLE_UNTIL_SETTINGS
    return now + _WAITING_INPUTS


def _is_stable_config_skip(lower: str) -> bool:
    return (
        "no model selected" in lower
        or "model is disabled" in lower
        or "model no longer exists" in lower
    )
