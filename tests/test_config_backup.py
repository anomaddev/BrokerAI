from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.config_backup.incremental_payload import (
    extract_incremental_payload,
    merge_incremental,
    resolve_payload_at_change,
)
from brokerai.config_backup.restore_scopes import extract_scoped_sections
from brokerai.config_backup.service import AUTO_BACKUP_RETENTION, ConfigBackupService
from brokerai.config_backup.summary import summarize_payload
from brokerai.config_backup.validate import parse_import_bytes, validate_payload
from brokerai.db.repositories.config_backups import ConfigBackupsRepository


def _sample_payload() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "user_preferences": {
            "general_settings": {
                "timezone_auto": True,
                "timezone": "America/New_York",
                "show_utc_times": False,
                "time_format": "24h",
            },
            "market_indicators": {"sydney": True, "london": True},
        },
        "system_settings": {
            "update_track": "branch",
            "branch": "main",
            "release": "",
            "auto_update": True,
        },
        "asset_settings": [{"asset_class": "forex", "enabled": True, "enabled_pairs": ["EUR/USD"]}],
        "strategies": [{"id": "s1", "name": "Test", "enabled": True, "params": {}}],
        "exchange_connections": [{"exchange_id": "oanda", "access_token": "tok"}],
        "research_settings": {"id": "default", "daily_report_enabled": False},
        "data_connections": [{"id": "default", "type": "newsapi", "enabled": False}],
        "ai_models": [{"id": "m1", "title": "Model", "enabled": True}],
    }


def _match_query(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        value = doc.get(key)
        if isinstance(expected, dict):
            if "$in" in expected:
                if value not in expected["$in"]:
                    return False
            elif "$lte" in expected:
                if value is None or value > expected["$lte"]:
                    return False
            elif "$gt" in expected:
                if value is None or value <= expected["$gt"]:
                    return False
            elif "$gte" in expected:
                if value is None or value < expected["$gte"]:
                    return False
            else:
                if not all(doc.get(k) == v for k, v in expected.items()):
                    return False
        elif value != expected:
            return False
    return True


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    async def insert_one(self, doc: dict[str, Any]) -> MagicMock:
        self.docs.append(dict(doc))
        return MagicMock(inserted_id="fake")

    async def find_one(
        self,
        query: dict[str, Any],
        projection: dict[str, Any] | None = None,
        sort: list[tuple[str, int]] | None = None,
    ) -> dict[str, Any] | None:
        matched = [doc for doc in self.docs if _match_query(doc, query)]
        if sort:
            field, direction = sort[0]
            matched.sort(key=lambda doc: doc.get(field) or "", reverse=direction < 0)
        if not matched:
            return None
        doc = matched[0]
        if projection and projection.get("payload") == 0:
            return {k: v for k, v in doc.items() if k != "payload" and k != "_id"}
        if projection:
            return {k: v for k, v in doc.items() if k != "_id"}
        return dict(doc)

    def find(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        matched = [doc for doc in self.docs if _match_query(doc, query)]

        cursor = MagicMock()
        sort_field: str | None = None
        sort_dir = 1
        limit_value: int | None = None
        skip_value = 0

        def sort(field: str, direction: int = 1):
            nonlocal sort_field, sort_dir
            if isinstance(field, list):
                sort_field, sort_dir = field[0]
            else:
                sort_field, sort_dir = field, direction
            return cursor

        def skip(value: int):
            nonlocal skip_value
            skip_value = value
            return cursor

        def limit(value: int):
            nonlocal limit_value
            limit_value = value
            return cursor

        async def to_list(length: int | None = None):
            rows = list(matched)
            if sort_field:
                rows.sort(key=lambda doc: doc.get(sort_field) or "", reverse=sort_dir < 0)
            if skip_value:
                rows = rows[skip_value:]
            cap = limit_value or length or len(rows)
            sliced = rows[:cap]
            if projection and projection.get("payload") == 0:
                return [{k: v for k, v in doc.items() if k != "payload" and k != "_id"} for doc in sliced]
            if projection:
                return [{k: v for k, v in doc.items() if k != "_id"} for doc in sliced]
            return [dict(doc) for doc in sliced]

        cursor.sort = sort
        cursor.skip = skip
        cursor.limit = limit
        cursor.to_list = to_list
        return cursor

    async def count_documents(self, query: dict[str, Any]) -> int:
        if not query:
            return len(self.docs)
        return sum(1 for doc in self.docs if _match_query(doc, query))

    async def delete_one(self, query: dict[str, Any]) -> MagicMock:
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not _match_query(doc, query)]
        deleted = before - len(self.docs)
        return MagicMock(deleted_count=deleted)

    async def delete_many(self, query: dict[str, Any]) -> MagicMock:
        before = len(self.docs)
        if not query:
            self.docs = []
        else:
            self.docs = [doc for doc in self.docs if not _match_query(doc, query)]
        return MagicMock(deleted_count=before - len(self.docs))

    async def insert_many(self, docs: list[dict[str, Any]]) -> MagicMock:
        self.docs.extend(dict(doc) for doc in docs)
        return MagicMock(inserted_ids=list(range(len(docs))))

    async def update_one(self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False) -> MagicMock:
        matched = [doc for doc in self.docs if _match_query(doc, query)]
        if matched:
            matched[0].update(update.get("$set", {}))
            return MagicMock(matched_count=1, modified_count=1)
        if upsert:
            self.docs.append(dict(update.get("$set", {})))
            return MagicMock(matched_count=0, modified_count=0, upserted_id="new")
        return MagicMock(matched_count=0, modified_count=0)


class _FakeDb:
    def __init__(self) -> None:
        self.config_backups = _FakeCollection()
        self.backup_settings = _FakeCollection()
        self.asset_settings = _FakeCollection()
        self.strategies = _FakeCollection()
        self.exchange_connections = _FakeCollection()
        self.research_settings = _FakeCollection()
        self.data_connections = _FakeCollection()
        self.ai_models = _FakeCollection()
        self.broker_lots = _FakeCollection()

    def __getitem__(self, name: str) -> _FakeCollection:
        return getattr(self, name)


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
    repo = ConfigBackupsRepository()
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
async def test_create_manual_backup_stores_full_payload(fake_db: _FakeDb, service: ConfigBackupService):
    fake_db.strategies.docs = [{"id": "s1", "name": "EMA"}]

    with patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))):
        backup = await service.create_manual_backup(label="Before tweak")

    assert backup["kind"] == "full"
    assert backup["source"] == "manual"
    assert backup["payload_type"] == "full"
    assert backup["label"] == "Before tweak"
    assert backup["payload"]["strategies"][0]["id"] == "s1"
    assert backup["change_label"] == "Manual backup"
    assert backup["category"] == "Backup"


@pytest.mark.asyncio
async def test_auto_backup_before_stores_incremental_change(fake_db: _FakeDb, service: ConfigBackupService):
    payload = _sample_payload()
    with patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))):
        with patch.object(service, "capture_snapshot", AsyncMock(return_value=payload)):
            await service.create_manual_backup(label="base")
            change = await service.auto_backup_before(
                trigger="account.general",
                summary="General settings",
                change_label="Timezone set to UTC",
            )

    assert change["kind"] == "change"
    assert change["payload_type"] == "incremental"
    assert "general_settings" in change["payload"]["user_preferences"]
    assert "market_indicators" not in (change["payload"].get("user_preferences") or {})
    assert change["base_backup_id"]


@pytest.mark.asyncio
async def test_list_backups_splits_changes_and_full(fake_db: _FakeDb, service: ConfigBackupService):
    with patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))):
        await service._repo.insert(
            kind="full",
            trigger="manual",
            summary="full",
            payload={"schema_version": 2},
            source="manual",
            payload_type="full",
        )
        await service._repo.insert(
            kind="change",
            trigger="account.general",
            summary="change",
            payload={"schema_version": 2, "user_preferences": {"general_settings": {}}},
            payload_type="incremental",
        )
        result = await service.list_backups()

    assert len(result["full_backups"]) == 1
    assert len(result["changes"]) == 1


@pytest.mark.asyncio
async def test_list_timeline_all(fake_db: _FakeDb, service: ConfigBackupService):
    with patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))):
        for index in range(30):
            await service._repo.insert(
                kind="change",
                trigger=f"t{index}",
                summary=f"change {index}",
                payload={"schema_version": 2},
                payload_type="incremental",
            )
        timeline = await service.list_timeline_all()

    assert len(timeline["items"]) == 30
    assert timeline["total"] == 30


@pytest.mark.asyncio
async def test_summarize_payload_lists_all_areas():
    areas = summarize_payload(_sample_payload())
    assert "General" in areas
    assert "Display" in areas
    assert "System updates" in areas
    assert any(area.startswith("Strategies") for area in areas)


def test_extract_scoped_sections_general_only():
    payload = _sample_payload()
    scoped = extract_scoped_sections(payload, "account.general")
    assert scoped["user_preferences"]["general_settings"]["timezone"] == "America/New_York"
    assert "market_indicators" not in scoped["user_preferences"]


def test_merge_incremental_overlays_general_settings():
    base = _sample_payload()
    overlay = extract_scoped_sections(
        {
            **base,
            "user_preferences": {
                **base["user_preferences"],
                "general_settings": {
                    **base["user_preferences"]["general_settings"],
                    "timezone": "UTC",
                },
            },
        },
        "account.general",
    )
    merged = merge_incremental(base, overlay)
    assert merged["user_preferences"]["general_settings"]["timezone"] == "UTC"
    assert merged["user_preferences"]["market_indicators"]["sydney"] is True


@pytest.mark.asyncio
async def test_restore_user_preferences(fake_db: _FakeDb, service: ConfigBackupService):
    from brokerai.auth.store import UserRecord

    current = UserRecord(
        username="admin",
        password_hash="hash",
        created_at="2026-01-01T00:00:00Z",
        timezone_auto=True,
        timezone="UTC",
        show_utc_times=True,
        time_format="12h",
        market_indicators={"sydney": False},
    )
    payload = _sample_payload()
    mock_store = MagicMock()
    mock_store.get_user.return_value = current
    mock_store._save_user.side_effect = lambda record: record

    with (
        patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))),
        patch("brokerai.config_backup.service.get_db", AsyncMock(return_value=MagicMock(db=fake_db))),
        patch("brokerai.config_backup.service.AuthStore", return_value=mock_store),
        patch("brokerai.config_backup.service.config_file_writable", return_value=False),
    ):
        backup = await service._repo.insert(
            kind="full",
            trigger="test",
            summary="test",
            payload=payload,
            label="prefs",
            payload_type="full",
            source="manual",
        )
        await service.restore_backup(backup["id"])

    saved = mock_store._save_user.call_args[0][0]
    assert saved.timezone == "America/New_York"
    assert saved.time_format == "24h"
    assert saved.market_indicators["sydney"] is True


@pytest.mark.asyncio
async def test_restore_backup_replaces_collections(fake_db: _FakeDb, service: ConfigBackupService):
    fake_db.strategies.docs = [{"id": "old", "name": "Old"}]
    payload = _sample_payload()

    with (
        patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))),
        patch("brokerai.config_backup.service.get_db", AsyncMock(return_value=MagicMock(db=fake_db))),
        patch.object(service, "capture_snapshot", AsyncMock(return_value=payload)),
    ):
        backup = await service._repo.insert(
            kind="full",
            trigger="test",
            summary="test",
            payload=payload,
            label="good",
            payload_type="full",
            source="manual",
        )
        fake_db.strategies.docs = [{"id": "bad", "name": "Bad"}]
        result = await service.restore_backup(backup["id"])

    assert result["restored_id"] == backup["id"]
    assert result["safety_backup_id"]
    assert fake_db.strategies.docs == payload["strategies"]
    assert fake_db.asset_settings.docs == payload["asset_settings"]
    assert len(fake_db.config_backups.docs) == 2


@pytest.mark.asyncio
async def test_change_backup_prunes_oldest(fake_db: _FakeDb, service: ConfigBackupService):
    with (
        patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))),
        patch(
            "brokerai.config_backup.service.get_backup_schedule_settings",
            AsyncMock(return_value={"change_retention": AUTO_BACKUP_RETENTION, "full_retention": 30}),
        ),
    ):
        for index in range(AUTO_BACKUP_RETENTION + 5):
            await service.create_backup(
                kind="change",
                trigger=f"t{index}",
                summary=f"auto {index}",
                payload={"schema_version": 2},
                payload_type="incremental",
            )

    change_backups = [doc for doc in fake_db.config_backups.docs if doc["kind"] == "change"]
    assert len(change_backups) == AUTO_BACKUP_RETENTION


@pytest.mark.asyncio
async def test_ensure_baseline_backup_creates_once(fake_db: _FakeDb, service: ConfigBackupService):
    with (
        patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))),
        patch("brokerai.config_backup.service.get_db", AsyncMock(return_value=MagicMock(db=fake_db))),
    ):
        first = await service.ensure_baseline_backup()
        second = await service.ensure_baseline_backup()

    assert first is not None
    assert first["label"] == "Initial baseline"
    assert first["kind"] == "full"
    assert second is None
    assert len(fake_db.config_backups.docs) == 1


@pytest.mark.asyncio
async def test_restore_does_not_touch_broker_lots(fake_db: _FakeDb, service: ConfigBackupService):
    fake_db.broker_lots.docs = [{"id": "lot-1"}]
    payload = _sample_payload()

    with (
        patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))),
        patch("brokerai.config_backup.service.get_db", AsyncMock(return_value=MagicMock(db=fake_db))),
    ):
        with patch.object(service, "capture_snapshot", AsyncMock(return_value=payload)):
            backup = await service.create_manual_backup(label="snapshot")
        await service.restore_backup(backup["id"])

    assert fake_db.broker_lots.docs == [{"id": "lot-1"}]


@pytest.mark.asyncio
async def test_resolve_payload_at_change_reconstructs_state(fake_db: _FakeDb, service: ConfigBackupService):
    payload = _sample_payload()
    with patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))):
        base = await service._repo.insert(
            kind="full",
            trigger="manual",
            summary="base",
            payload=payload,
            payload_type="full",
            source="manual",
        )
        general_overlay = extract_incremental_payload(payload, "account.general")
        general_overlay["user_preferences"]["general_settings"]["timezone"] = "Europe/London"
        change = await service._repo.insert(
            kind="change",
            trigger="account.general",
            summary="general",
            payload=general_overlay,
            payload_type="incremental",
            base_backup_id=base["id"],
        )
        resolved = await resolve_payload_at_change(change["id"], repo=service._repo)

    assert resolved["user_preferences"]["general_settings"]["timezone"] == "Europe/London"


def test_parse_import_bytes_accepts_record_shape():
    payload = _sample_payload()
    raw = parse_import_bytes(
        __import__("json").dumps({"payload": payload, "schema_version": 2}).encode("utf-8")
    )
    assert payload["strategies"][0]["id"] == validate_payload(payload)["strategies"][0]["id"]
    assert raw["asset_settings"]


def test_parse_import_bytes_rejects_invalid_schema():
    with pytest.raises(ValueError, match="Unsupported backup schema"):
        parse_import_bytes(__import__("json").dumps({"schema_version": 99}).encode("utf-8"))


def _general_snapshot(*, show_utc: bool) -> dict[str, Any]:
    payload = _sample_payload()
    payload["user_preferences"]["general_settings"]["show_utc_times"] = show_utc
    return payload


@pytest.mark.asyncio
async def test_auto_backup_before_flattens_redundant_toggle_pair(fake_db: _FakeDb, service: ConfigBackupService):
    snapshots = [
        _sample_payload(),
        _general_snapshot(show_utc=False),
        _general_snapshot(show_utc=True),
        _general_snapshot(show_utc=False),
        _general_snapshot(show_utc=True),
    ]
    with patch("brokerai.db.repositories.config_backups.get_db", AsyncMock(return_value=MagicMock(db=fake_db))):
        with patch.object(service, "capture_snapshot", AsyncMock(side_effect=snapshots)):
            await service.create_manual_backup(label="base")
            first = await service.auto_backup_before(
                trigger="account.general",
                summary="General settings",
                change_label="UTC times enabled",
            )
            second = await service.auto_backup_before(
                trigger="account.general",
                summary="General settings",
                change_label="UTC times disabled",
            )
            third = await service.auto_backup_before(
                trigger="account.general",
                summary="General settings",
                change_label="UTC times enabled",
            )
            fourth = await service.auto_backup_before(
                trigger="account.general",
                summary="General settings",
                change_label="UTC times disabled",
            )

    assert first is not None
    assert second is not None
    assert third is None
    assert fourth is not None

    change_backups = [doc for doc in fake_db.config_backups.docs if doc["kind"] == "change"]
    assert len(change_backups) == 2
    assert change_backups[0]["change_label"] == "UTC times enabled"
    assert change_backups[1]["change_label"] == "UTC times disabled"
