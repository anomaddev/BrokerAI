"""Secretary scheduled-research probe deferral."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from brokerai.bots.secretary.scheduled_research import (
    after_launch_deferral,
    next_brief_probe_at,
    next_daily_probe_at,
    next_debrief_probe_at,
    next_debrief_schedule_probe_at,
    research_settings_fingerprint,
)


def test_fingerprint_changes_when_debrief_model_set() -> None:
    base = {
        "weekly_debrief_enabled": True,
        "weekly_debrief_model_id": None,
        "last_weekly_debrief_run_week": None,
    }
    updated = {**base, "weekly_debrief_model_id": "model-1"}
    assert research_settings_fingerprint(base) != research_settings_fingerprint(updated)


def test_debrief_no_model_defers_until_settings_change() -> None:
    now = datetime(2026, 7, 19, 14, 0, tzinfo=timezone.utc)
    settings = {
        "weekly_debrief_market_id": "london",
        "weekly_debrief_market_offset_hours": 1,
    }
    until = next_debrief_probe_at(
        now, settings, "No model selected for weekly_debrief_model_id"
    )
    assert until.year == 9999


def test_debrief_already_ran_defers_to_next_slot() -> None:
    now = datetime(2026, 7, 19, 14, 0, tzinfo=timezone.utc)
    settings = {
        "weekly_debrief_market_id": "london",
        "weekly_debrief_market_offset_hours": 1,
    }
    until = next_debrief_probe_at(now, settings, "Weekly debrief already ran for 2026-W29")
    assert until > now
    assert until.year != 9999


def test_debrief_insufficient_dailies_uses_waiting_backoff() -> None:
    now = datetime(2026, 7, 19, 14, 0, tzinfo=timezone.utc)
    settings = {
        "weekly_debrief_market_id": "london",
        "weekly_debrief_market_offset_hours": 1,
    }
    until = next_debrief_probe_at(
        now, settings, "Insufficient weekday dailies for week 2026-W29"
    )
    assert until == now + timedelta(minutes=30)


def test_debrief_launch_uses_short_backoff() -> None:
    now = datetime(2026, 7, 19, 14, 0, tzinfo=timezone.utc)
    settings = {
        "weekly_debrief_market_id": "london",
        "weekly_debrief_market_offset_hours": 1,
    }
    assert next_debrief_probe_at(now, settings, None) == after_launch_deferral(now)


def test_debrief_schedule_probe_is_in_the_future_when_due_week_absent() -> None:
    # Monday morning before Friday close — next slot should be this week's Friday+.
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
    settings = {
        "weekly_debrief_market_id": "london",
        "weekly_debrief_market_offset_hours": 1,
    }
    until = next_debrief_schedule_probe_at(now, settings)
    assert until > now


def test_daily_done_defers_to_tomorrow_slot() -> None:
    now = datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc)
    settings = {
        "daily_report_market_id": "london",
        "daily_report_market_offset_hours": -2,
    }
    until = next_daily_probe_at(now, settings, done_today=True)
    assert until.date() >= now.date() + timedelta(days=1)


def test_brief_missing_open_day_uses_waiting_backoff() -> None:
    now = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    settings = {
        "weekly_brief_market_id": "london",
        "weekly_brief_market_offset_hours": -1,
    }
    until = next_brief_probe_at(
        now, settings, "Open-day daily report missing for 2026-07-20"
    )
    assert until == now + timedelta(minutes=30)
