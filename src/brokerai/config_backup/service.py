from __future__ import annotations

import logging
from typing import Any, Literal

from sqlalchemy import delete, select

from brokerai.auth.store import AuthStore
from brokerai.config.env_file import config_file_writable, save_update_env_values
from brokerai.config.settings import get_settings, reload_settings
from brokerai.config_backup.categories import category_for_trigger
from brokerai.config_backup.change_history_flatten import (
    CHANGE_FLATTEN_WINDOW,
    find_redundant_change_ids,
)
from brokerai.config_backup.incremental_payload import (
    extract_incremental_payload,
    resolve_payload_at_change,
)
from brokerai.config_backup.schedule_settings import (
    get_backup_schedule_settings,
    is_scheduled_backup_due,
    mark_scheduled_backup_ran,
    save_backup_schedule_settings,
    schedule_settings_payload,
)
from brokerai.config_backup.summary import summarize_payload
from brokerai.config_backup.validate import validate_payload
from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import (
    AiModelRow,
    AssetSettingsRow,
    DataConnectionRow,
    ExchangeConnectionRow,
    ResearchSettingsRow,
    StrategyRow,
)
from brokerai.db.repositories.ai_models import AiModelsRepository
from brokerai.db.repositories.strategies import _sync_row_columns
from brokerai.db.repositories.asset_settings import ASSET_CLASSES, AssetSettingsRepository
from brokerai.db.repositories.config_backups import (
    DEFAULT_CHANGE_RETENTION as REPO_DEFAULT_CHANGE_RETENTION,
    DEFAULT_FULL_RETENTION as REPO_DEFAULT_FULL_RETENTION,
    ConfigBackupsRepository,
    SCHEMA_VERSION,
)
from brokerai.db.repositories.research_settings import (
    SINGLETON_ID as RESEARCH_SINGLETON_ID,
    ResearchSettingsRepository,
)
from brokerai.market_sessions import normalize_market_indicators
from brokerai.web.update_runner import clear_update_check_cache

logger = logging.getLogger(__name__)

AUTO_BACKUP_RETENTION = REPO_DEFAULT_CHANGE_RETENTION
FULL_BACKUP_RETENTION = REPO_DEFAULT_FULL_RETENTION
BASELINE_LABEL = "Initial baseline"

RestoreScope = Literal["setting", "full"]


def _strip_id(doc: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in doc.items() if key != "_id"}


def _asset_settings_row(doc: dict[str, Any]) -> AssetSettingsRow:
    cleaned = _strip_id(doc)
    return AssetSettingsRow(asset_class=str(cleaned["asset_class"]), doc=cleaned)


def _strategy_row(doc: dict[str, Any]) -> StrategyRow:
    cleaned = _strip_id(doc)
    row = StrategyRow(
        id=str(cleaned["id"]),
        asset_class=str(cleaned["asset_class"]),
        name=str(cleaned["name"]),
        enabled=bool(cleaned.get("enabled", False)),
        preset_id=cleaned.get("preset_id"),
        doc=cleaned,
    )
    _sync_row_columns(row, cleaned)
    return row


def _exchange_connection_row(doc: dict[str, Any]) -> ExchangeConnectionRow:
    cleaned = _strip_id(doc)
    exchange_id = str(cleaned.get("exchange_id") or "")
    return ExchangeConnectionRow(exchange_id=exchange_id, doc=cleaned)


def _data_connection_row(doc: dict[str, Any]) -> DataConnectionRow:
    cleaned = _strip_id(doc)
    conn_type = str(cleaned.get("type") or cleaned.get("conn_type") or "")
    model_id = cleaned.get("model_id")
    return DataConnectionRow(
        conn_type=conn_type,
        model_id=str(model_id) if model_id else None,
        doc=cleaned,
    )


def _research_settings_row(doc: dict[str, Any]) -> ResearchSettingsRow:
    cleaned = _strip_id(doc)
    return ResearchSettingsRow(id=str(cleaned.get("id") or RESEARCH_SINGLETON_ID), doc=cleaned)


def _ai_model_row(doc: dict[str, Any]) -> AiModelRow:
    cleaned = _strip_id(doc)
    return AiModelRow(
        id=str(cleaned["id"]),
        enabled=bool(cleaned.get("enabled", True)),
        created_at=str(cleaned.get("created_at") or ""),
        doc=cleaned,
    )


async def _list_strategy_docs() -> list[dict[str, Any]]:
    async with session_scope() as session:
        rows = (await session.execute(select(StrategyRow))).scalars().all()
        return [dict(row.doc) for row in rows]


async def _list_exchange_connection_docs() -> list[dict[str, Any]]:
    async with session_scope() as session:
        rows = (await session.execute(select(ExchangeConnectionRow))).scalars().all()
        return [dict(row.doc) for row in rows]


async def _list_data_connection_docs() -> list[dict[str, Any]]:
    async with session_scope() as session:
        rows = (await session.execute(select(DataConnectionRow))).scalars().all()
        return [dict(row.doc) for row in rows]


async def _replace_asset_settings(session, docs: list[dict[str, Any]]) -> None:
    await session.execute(delete(AssetSettingsRow))
    for doc in docs:
        session.add(_asset_settings_row(doc))


async def _replace_strategies(session, docs: list[dict[str, Any]]) -> None:
    await session.execute(delete(StrategyRow))
    for doc in docs:
        session.add(_strategy_row(doc))


async def _replace_exchange_connections(session, docs: list[dict[str, Any]]) -> None:
    await session.execute(delete(ExchangeConnectionRow))
    for doc in docs:
        session.add(_exchange_connection_row(doc))


async def _replace_data_connections(session, docs: list[dict[str, Any]]) -> None:
    await session.execute(delete(DataConnectionRow))
    for doc in docs:
        session.add(_data_connection_row(doc))


async def _replace_research_settings(session, doc: dict[str, Any] | None) -> None:
    await session.execute(delete(ResearchSettingsRow))
    if isinstance(doc, dict) and doc:
        session.add(_research_settings_row(doc))


async def _replace_ai_models(session, docs: list[dict[str, Any]]) -> None:
    await session.execute(delete(AiModelRow))
    for doc in docs:
        session.add(_ai_model_row(doc))


def _backup_summary(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Timeline metadata without payload."""
    if not doc:
        return None
    return {key: value for key, value in doc.items() if key != "payload"}


class ConfigBackupService:
    """Capture, store, and restore dashboard configuration snapshots."""

    def __init__(self, repo: ConfigBackupsRepository | None = None) -> None:
        self._repo = repo or ConfigBackupsRepository()

    def _capture_user_preferences(self) -> dict[str, Any] | None:
        user = AuthStore().get_user()
        if user is None:
            return None
        return {
            "general_settings": user.resolved_general_settings(),
            "market_indicators": user.resolved_market_indicators(),
        }

    def _capture_system_settings(self) -> dict[str, Any] | None:
        settings = get_settings()
        return {
            "update_track": settings.update_track,
            "branch": settings.branch,
            "release": settings.release or "",
            "auto_update": settings.auto_update,
        }

    async def capture_snapshot(self) -> dict[str, Any]:
        """Read current Postgres and file-based settings into a versioned payload."""
        asset_settings: list[dict[str, Any]] = []
        asset_repo = AssetSettingsRepository()
        for asset_class in ASSET_CLASSES:
            doc = await asset_repo.get(asset_class)
            asset_settings.append(doc)

        strategies = await _list_strategy_docs()
        exchange_connections = await _list_exchange_connection_docs()
        research_settings = await ResearchSettingsRepository().get()
        data_connections = await _list_data_connection_docs()
        ai_models = await AiModelsRepository().list_all()

        return {
            "schema_version": SCHEMA_VERSION,
            "user_preferences": self._capture_user_preferences(),
            "system_settings": self._capture_system_settings(),
            "asset_settings": asset_settings,
            "strategies": strategies,
            "exchange_connections": exchange_connections,
            "research_settings": research_settings,
            "data_connections": data_connections,
            "ai_models": ai_models,
        }

    async def _retention_limits(self) -> tuple[int, int]:
        schedule = await get_backup_schedule_settings()
        change_limit = int(schedule.get("change_retention") or REPO_DEFAULT_CHANGE_RETENTION)
        full_limit = int(schedule.get("full_retention") or REPO_DEFAULT_FULL_RETENTION)
        return change_limit, full_limit

    async def create_backup(
        self,
        *,
        kind: str,
        trigger: str,
        summary: str,
        payload: dict[str, Any],
        label: str | None = None,
        change_label: str | None = None,
        payload_type: str = "full",
        base_backup_id: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        included_areas = summarize_payload(payload)
        backup = await self._repo.insert(
            kind=kind,  # type: ignore[arg-type]
            trigger=trigger,
            summary=summary,
            payload=payload,
            label=label,
            included_areas=included_areas,
            change_label=change_label or summary,
            category=category_for_trigger(trigger),
            payload_type=payload_type,  # type: ignore[arg-type]
            base_backup_id=base_backup_id,
            source=source,  # type: ignore[arg-type]
        )
        if kind == "change":
            await self._prune_change_backups()
        elif kind == "full":
            await self._prune_full_backups()
        return backup

    async def auto_backup_before(
        self,
        *,
        trigger: str,
        summary: str,
        change_label: str | None = None,
    ) -> dict[str, Any] | None:
        """Snapshot scoped config sections before a mutation is applied."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        full_snapshot = await self.capture_snapshot()
        incremental = extract_incremental_payload(full_snapshot, trigger)

        recent = await self._repo.list_changes_since(
            now - CHANGE_FLATTEN_WINDOW,
            include_payload=True,
        )
        redundant_ids = find_redundant_change_ids(
            recent,
            trigger=trigger,
            new_payload=incremental,
            now=now,
        )
        if redundant_ids:
            for redundant_id in redundant_ids:
                await self._repo.delete_by_id(redundant_id)
            logger.debug(
                "Flattened redundant change history for trigger %s (dropped %s)",
                trigger,
                ", ".join(redundant_ids),
            )
            return None

        base = await self._repo.find_latest_full_before(
            now,
            include_payload=False,
        )
        base_id = str(base["id"]) if base and base.get("id") else None

        return await self.create_backup(
            kind="change",
            trigger=trigger,
            summary=summary,
            payload=incremental,
            change_label=change_label,
            payload_type="incremental",
            base_backup_id=base_id,
        )

    async def create_manual_backup(self, *, label: str | None = None) -> dict[str, Any]:
        summary = label.strip() if label and label.strip() else "Manual backup"
        payload = await self.capture_snapshot()
        return await self.create_backup(
            kind="full",
            trigger="manual",
            summary=summary,
            payload=payload,
            label=label,
            change_label="Manual backup",
            payload_type="full",
            source="manual",
        )

    async def create_scheduled_backup(self) -> dict[str, Any] | None:
        payload = await self.capture_snapshot()
        return await self.create_backup(
            kind="full",
            trigger="schedule",
            summary="Scheduled backup",
            payload=payload,
            change_label="Scheduled backup",
            payload_type="full",
            source="scheduled",
        )

    async def import_backup(
        self,
        payload: dict[str, Any],
        *,
        label: str | None = None,
        restore_immediately: bool = False,
    ) -> dict[str, Any]:
        validated = validate_payload(payload)
        summary = label.strip() if label and label.strip() else "Imported backup"
        safety: dict[str, Any] | None = None
        safety_id: str | None = None
        if restore_immediately:
            safety = await self.auto_backup_before(
                trigger="restore",
                summary="Before import restore",
            )
            safety_id = str(safety.get("id")) if safety and safety.get("id") else None

        backup = await self.create_backup(
            kind="full",
            trigger="import",
            summary=summary,
            payload=validated,
            label=label,
            change_label="Imported backup",
            payload_type="full",
            source="import",
        )

        restored = False
        if restore_immediately:
            await self._apply_payload(validated)
            restored = True

        return {
            "backup": _backup_summary(backup) or backup,
            "restored": restored,
            "safety_backup_id": safety_id,
            "safety_backup": _backup_summary(safety),
        }

    async def ensure_baseline_backup(self) -> dict[str, Any] | None:
        """Create an initial baseline when no backups exist yet."""
        if await self._repo.count() > 0:
            return None
        payload = await self.capture_snapshot()
        return await self.create_backup(
            kind="full",
            trigger="baseline",
            summary=BASELINE_LABEL,
            payload=payload,
            label=BASELINE_LABEL,
            change_label=BASELINE_LABEL,
            payload_type="full",
            source="baseline",
        )

    async def list_backups(self) -> dict[str, list[dict[str, Any]]]:
        await self.ensure_baseline_backup()
        changes = await self._repo.list_by_kind("change")
        full_backups = await self._repo.list_by_kind("full")
        return {"changes": changes, "full_backups": full_backups}

    async def list_timeline(self, *, page: int = 1, limit: int = 25) -> dict[str, Any]:
        await self.ensure_baseline_backup()
        return await self._repo.list_timeline_page(page=page, limit=limit)

    async def list_timeline_all(self) -> dict[str, Any]:
        """Return the full backup timeline for client-side paging."""
        await self.ensure_baseline_backup()
        items = await self._repo.list_metadata()
        return {"items": items, "total": len(items)}

    async def get_backup(self, backup_id: str) -> dict[str, Any] | None:
        return await self._repo.get_by_id(backup_id, include_payload=True)

    async def export_current(self) -> dict[str, Any]:
        payload = await self.capture_snapshot()
        from datetime import datetime, timezone

        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "full",
            "payload_type": "full",
            "source": "export",
            "trigger": "export",
            "summary": "Current configuration export",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "included_areas": summarize_payload(payload),
            "payload": payload,
        }

    async def delete_backup(self, backup_id: str) -> bool:
        return await self._repo.delete_by_id(backup_id)

    async def restore_backup(
        self,
        backup_id: str,
        *,
        scope: RestoreScope = "full",
        skip_safety: bool = False,
    ) -> dict[str, Any]:
        """Restore configuration from a backup after creating a pre-restore safety snapshot."""
        backup = await self._repo.get_by_id(backup_id, include_payload=True)
        if not backup:
            raise ValueError(f"Backup not found: {backup_id}")

        safety: dict[str, Any] | None = None
        safety_id: str | None = None
        if not skip_safety:
            safety = await self.auto_backup_before(
                trigger="restore",
                summary=f"Before restore to {backup.get('label') or backup.get('summary') or backup_id}",
            )
            safety_id = str(safety.get("id")) if safety and safety.get("id") else None

        kind = backup.get("kind")
        if scope == "setting" and kind == "change":
            payload = backup.get("payload") or {}
            await self._apply_scoped_payload(payload)
        elif scope == "full" and kind == "change":
            payload = await resolve_payload_at_change(backup_id, repo=self._repo)
            await self._apply_payload(payload)
        else:
            payload = backup.get("payload") or {}
            await self._apply_payload(payload)

        return {
            "restored_id": backup_id,
            "safety_backup_id": safety_id,
            "safety_backup": _backup_summary(safety),
            "summary": backup.get("summary"),
            "scope": scope,
        }

    async def run_scheduled_backup_if_due(self) -> dict[str, Any] | None:
        settings = await get_backup_schedule_settings()
        if not is_scheduled_backup_due(settings):
            return None

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        if settings.get("mode") == "interval":
            last_raw = settings.get("last_scheduled_at")
            if last_raw:
                try:
                    last = datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    window_start = last
                except ValueError:
                    window_start = now - __import__("datetime").timedelta(hours=int(settings["interval_hours"]))
            else:
                window_start = now - __import__("datetime").timedelta(hours=int(settings["interval_hours"]))
        else:
            from brokerai.config_backup.schedule_settings import _scheduled_run_for_settings

            window_start = _scheduled_run_for_settings(settings, now=now)

        recent = await self._repo.find_latest_full_before(now, include_payload=False)
        if recent:
            from brokerai.db.repositories.config_backups import parse_created_at

            recent_at = parse_created_at(recent.get("created_at"))
            if recent_at and recent_at >= window_start and recent.get("source") == "scheduled":
                await mark_scheduled_backup_ran(when=now)
                return None

        backup = await self.create_scheduled_backup()
        await mark_scheduled_backup_ran(when=now)
        return backup

    async def _restore_user_preferences(self, prefs: dict[str, Any] | None) -> None:
        if not prefs:
            return
        store = AuthStore()
        user = store.get_user()
        if user is None:
            return

        general = prefs.get("general_settings") or {}
        indicators = prefs.get("market_indicators")
        updated = user
        if general:
            updated = updated.replace(
                timezone_auto=bool(general.get("timezone_auto")),
                timezone=str(general["timezone"]) if general.get("timezone") else None,
                show_utc_times=bool(general.get("show_utc_times")),
                time_format=str(general.get("time_format") or "24h"),
            )
        if indicators is not None:
            updated = updated.replace(market_indicators=normalize_market_indicators(indicators))
        store._save_user(updated)

    async def _restore_system_settings(self, system: dict[str, Any] | None) -> None:
        if not isinstance(system, dict) or not system:
            return
        if not config_file_writable():
            logger.warning("Skipping system settings restore — config file is not writable")
            return
        settings = get_settings()
        auto_update = bool(system.get("auto_update"))
        if str(system.get("update_track")) == "release":
            auto_update = False
        save_update_env_values(
            update_track=str(system.get("update_track") or settings.update_track),
            branch=str(system.get("branch") or settings.branch),
            release=str(system.get("release") or ""),
            repo=settings.repo,
            auto_update=auto_update,
        )
        reload_settings()
        clear_update_check_cache()

    async def _apply_scoped_payload(self, payload: dict[str, Any]) -> None:
        """Apply only the sections present in a scoped/incremental payload."""
        if "user_preferences" in payload:
            await self._restore_user_preferences(payload.get("user_preferences"))
        if "system_settings" in payload:
            await self._restore_system_settings(payload.get("system_settings"))

        async with session_scope() as session:
            if "asset_settings" in payload:
                asset_settings = list(payload.get("asset_settings") or [])
                for doc in asset_settings:
                    asset_class = doc.get("asset_class")
                    if not asset_class:
                        continue
                    await session.execute(
                        delete(AssetSettingsRow).where(
                            AssetSettingsRow.asset_class == asset_class
                        )
                    )
                    session.add(_asset_settings_row(doc))

            if "strategies" in payload:
                strategies = list(payload.get("strategies") or [])
                await _replace_strategies(session, strategies)

            if "exchange_connections" in payload:
                exchange_connections = list(payload.get("exchange_connections") or [])
                await _replace_exchange_connections(session, exchange_connections)

            if "research_settings" in payload:
                research_settings = payload.get("research_settings")
                await _replace_research_settings(session, research_settings)

            if "data_connections" in payload:
                data_connections = list(payload.get("data_connections") or [])
                await _replace_data_connections(session, data_connections)

            if "ai_models" in payload:
                ai_models = list(payload.get("ai_models") or [])
                await _replace_ai_models(session, ai_models)

    async def _apply_payload(self, payload: dict[str, Any]) -> None:
        await self._restore_user_preferences(payload.get("user_preferences"))
        await self._restore_system_settings(payload.get("system_settings"))

        asset_settings = list(payload.get("asset_settings") or [])
        strategies = list(payload.get("strategies") or [])
        exchange_connections = list(payload.get("exchange_connections") or [])
        research_settings = payload.get("research_settings")
        data_connections = list(payload.get("data_connections") or [])
        ai_models = list(payload.get("ai_models") or [])

        async with session_scope() as session:
            await _replace_asset_settings(session, asset_settings)
            await _replace_strategies(session, strategies)
            await _replace_exchange_connections(session, exchange_connections)
            await _replace_research_settings(session, research_settings)
            await _replace_data_connections(session, data_connections)
            await _replace_ai_models(session, ai_models)

        logger.info(
            "Restored config backup: %d strategies, %d asset settings, %d exchange connections",
            len(strategies),
            len(asset_settings),
            len(exchange_connections),
        )

    async def _prune_change_backups(self) -> None:
        change_limit, _ = await self._retention_limits()
        change_ids = await self._repo.list_change_ids_oldest_first()
        excess = len(change_ids) - change_limit
        if excess <= 0:
            return
        for backup_id in change_ids[:excess]:
            await self._repo.delete_by_id(backup_id)
            logger.debug("Pruned change config backup %s", backup_id)

    async def _prune_full_backups(self) -> None:
        _, full_limit = await self._retention_limits()
        full_ids = await self._repo.list_full_ids_oldest_first()
        excess = len(full_ids) - full_limit
        if excess <= 0:
            return
        for backup_id in full_ids[:excess]:
            await self._repo.delete_by_id(backup_id)
            logger.debug("Pruned full config backup %s", backup_id)

    async def _prune_auto_backups(self) -> None:
        """Legacy alias."""
        await self._prune_change_backups()
