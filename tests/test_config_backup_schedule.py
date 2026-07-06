from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.config_backup.schedule_settings import (
    is_scheduled_backup_due,
    normalize_daily_time,
    normalize_schedule_settings,
    scheduled_local_time_utc,
)
from brokerai.config_backup.service import ConfigBackupService
from tests.test_config_backup import _FakeDb


def test_normalize_schedule_settings_defaults():
    settings = normalize_schedule_settings(None)
    assert settings["enabled"] is False
    assert settings["mode"] == "daily"
    assert settings["daily_time"] == "02:00"
    assert settings["interval_hours"] == 24
    assert settings["full_retention"] == 30
    assert settings["change_retention"] == 100


def test_normalize_daily_time():
    assert normalize_daily_time("3:5") == "03:05"
    assert normalize_daily_time("25:00") == "02:00"
    assert normalize_daily_time("invalid") == "02:00"


def test_normalize_retention_steps():
    from brokerai.config_backup.schedule_settings import (
        normalize_change_retention,
        normalize_full_retention,
    )

    assert normalize_full_retention(30) == 30
    assert normalize_full_retention(33) == 35
    assert normalize_full_retention(500) == 50
    assert normalize_full_retention(3) == 5
    assert normalize_change_retention(100) == 100
    assert normalize_change_retention(53) == 55
    assert normalize_change_retention(1000) == 100
    assert normalize_change_retention(10) == 20


def test_normalize_interval_hours_max_48():
    from brokerai.config_backup.schedule_settings import normalize_schedule_settings

    settings = normalize_schedule_settings({"interval_hours": 168})
    assert settings["interval_hours"] == 48


def test_daily_time_mode_not_due_before_scheduled():
    settings = normalize_schedule_settings(
        {"enabled": True, "mode": "daily_time", "daily_time": "23:59", "last_scheduled_at": None}
    )
    with patch(
        "brokerai.config_backup.schedule_settings.resolve_user_schedule_timezone",
        return_value="UTC",
    ):
        run_at = scheduled_local_time_utc("23:59", "UTC")
        assert is_scheduled_backup_due(settings, now=run_at - __import__("datetime").timedelta(minutes=1)) is False


def test_daily_time_mode_due_after_scheduled():
    settings = normalize_schedule_settings(
        {"enabled": True, "mode": "daily_time", "daily_time": "08:00", "last_scheduled_at": None}
    )
    with patch(
        "brokerai.config_backup.schedule_settings.resolve_user_schedule_timezone",
        return_value="UTC",
    ):
        run_at = scheduled_local_time_utc("08:00", "UTC")
        assert is_scheduled_backup_due(settings, now=run_at + __import__("datetime").timedelta(minutes=1)) is True


def test_interval_mode_due_when_never_ran():
    settings = normalize_schedule_settings({"enabled": True, "mode": "interval", "interval_hours": 6})
    assert is_scheduled_backup_due(settings, now=datetime.now(timezone.utc)) is True


@pytest.mark.asyncio
async def test_run_scheduled_backup_if_due_creates_full_backup():
    fake_db = _FakeDb()
    service = ConfigBackupService()

    async def capture_snapshot():
        return {"schema_version": 2, "strategies": [], "asset_settings": []}

    service.capture_snapshot = capture_snapshot  # type: ignore[method-assign]

    enabled_settings = normalize_schedule_settings(
        {"enabled": True, "mode": "interval", "interval_hours": 24, "last_scheduled_at": None}
    )

    with (
        patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=type("H", (), {"db": fake_db})())),
        patch("brokerai.config_backup.service.get_db", AsyncMock(return_value=type("H", (), {"db": fake_db})())),
        patch(
            "brokerai.config_backup.service.get_backup_schedule_settings",
            AsyncMock(return_value=enabled_settings),
        ),
        patch(
            "brokerai.config_backup.service.mark_scheduled_backup_ran",
            AsyncMock(),
        ),
    ):
        backup = await service.run_scheduled_backup_if_due()

    assert backup is not None
    assert backup["kind"] == "full"
    assert backup["source"] == "scheduled"
