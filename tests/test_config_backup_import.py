from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.config_backup.service import ConfigBackupService
from brokerai.config_backup.validate import parse_import_bytes
from tests.test_config_backup import (
    AUTO_BACKUP_RETENTION,
    _FakeDb,
    _sample_payload,
)


@pytest.fixture(autouse=True)
def _mock_backup_schedule_settings():
    with patch(
        "brokerai.config_backup.service.get_backup_schedule_settings",
        AsyncMock(
            return_value={
                "change_retention": AUTO_BACKUP_RETENTION,
                "full_retention": 30,
            }
        ),
    ):
        yield


@pytest.fixture
def fake_db() -> _FakeDb:
    return _FakeDb()


@pytest.fixture
def service(fake_db: _FakeDb) -> ConfigBackupService:
    repo = __import__(
        "brokerai.db.repositories.config_backups", fromlist=["ConfigBackupsRepository"]
    ).ConfigBackupsRepository()
    svc = ConfigBackupService(repo=repo)

    async def capture_snapshot() -> dict[str, Any]:
        return {
            "schema_version": 2,
            "user_preferences": None,
            "system_settings": None,
            "asset_settings": list(fake_db.asset_settings.docs),
            "strategies": list(fake_db.strategies.docs),
            "exchange_connections": list(fake_db.exchange_connections.docs),
            "research_settings": fake_db.research_settings.docs[0]
            if fake_db.research_settings.docs
            else None,
            "data_connections": list(fake_db.data_connections.docs),
            "ai_models": list(fake_db.ai_models.docs),
        }

    svc.capture_snapshot = capture_snapshot  # type: ignore[method-assign]
    return svc


@pytest.mark.asyncio
async def test_import_backup_creates_full_row(fake_db: _FakeDb, service: ConfigBackupService):
    payload = _sample_payload()
    with patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))):
        result = await service.import_backup(payload, label="From file")

    assert result["backup"]["kind"] == "full"
    assert result["backup"]["source"] == "import"
    assert result["restored"] is False
    assert result["backup"]["label"] == "From file"


@pytest.mark.asyncio
async def test_import_backup_restore_immediately(fake_db: _FakeDb, service: ConfigBackupService):
    payload = _sample_payload()
    fake_db.strategies.docs = [{"id": "live", "name": "Live"}]

    with (
        patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))),
        patch("brokerai.config_backup.service.get_db", AsyncMock(return_value=MagicMock(db=fake_db))),
    ):
        result = await service.import_backup(payload, restore_immediately=True)

    assert result["restored"] is True
    assert result["safety_backup_id"]
    assert fake_db.strategies.docs == payload["strategies"]


def test_parse_import_bytes_rejects_empty_payload():
    with pytest.raises(ValueError):
        parse_import_bytes(b'{"schema_version": 2}')
