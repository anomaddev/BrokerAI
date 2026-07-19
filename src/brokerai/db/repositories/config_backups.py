from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import delete, func, or_, select

from brokerai.config_backup.categories import category_for_trigger
from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import ConfigBackupRow

BackupKind = Literal["change", "full", "auto", "manual"]
PayloadType = Literal["full", "incremental"]
FullBackupSource = Literal["manual", "scheduled", "baseline", "import"]

SCHEMA_VERSION = 2

DEFAULT_CHANGE_RETENTION = 100
DEFAULT_FULL_RETENTION = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_created_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def normalize_backup_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    """Map legacy kinds and infer payload_type for API responses."""
    normalized = dict(doc)
    kind = str(normalized.get("kind") or "")

    if kind == "auto":
        normalized["kind"] = "change"
        if not normalized.get("payload_type"):
            normalized["payload_type"] = "full"
    elif kind == "manual":
        normalized["kind"] = "full"
        if not normalized.get("source"):
            trigger = str(normalized.get("trigger") or "")
            if trigger == "baseline":
                normalized["source"] = "baseline"
            else:
                normalized["source"] = "manual"
        if not normalized.get("payload_type"):
            normalized["payload_type"] = "full"
    elif kind == "full" and not normalized.get("payload_type"):
        normalized["payload_type"] = "full"
    elif kind == "change" and not normalized.get("payload_type"):
        normalized["payload_type"] = "incremental"

    return normalized


def _format_created_at_api(value: object) -> str:
    """Serialize backup timestamps as explicit UTC ISO-8601 for the dashboard."""
    parsed = parse_created_at(value)
    if parsed is None:
        return str(value or "")
    as_utc = parsed.astimezone(timezone.utc)
    text = as_utc.isoformat(timespec="milliseconds")
    return text.replace("+00:00", "Z")


def _serialize_backup(doc: dict[str, Any], *, include_payload: bool = True) -> dict[str, Any]:
    serialized = dict(doc)
    created_at = serialized.get("created_at")
    if created_at is not None:
        serialized["created_at"] = _format_created_at_api(created_at)
    if not include_payload:
        serialized.pop("payload", None)
    return normalize_backup_metadata(serialized)


def _change_kind_filter():
    return or_(ConfigBackupRow.kind == "change", ConfigBackupRow.kind == "auto")


def _full_kind_filter():
    return or_(ConfigBackupRow.kind == "full", ConfigBackupRow.kind == "manual")


class ConfigBackupsRepository:
    COLLECTION = "config_backups"

    async def count(self) -> int:
        async with session_scope() as session:
            stmt = select(func.count()).select_from(ConfigBackupRow)
            return int((await session.execute(stmt)).scalar_one())

    async def insert(
        self,
        *,
        kind: BackupKind,
        trigger: str,
        summary: str,
        payload: dict[str, Any],
        label: str | None = None,
        included_areas: list[str] | None = None,
        change_label: str | None = None,
        category: str | None = None,
        payload_type: PayloadType = "full",
        base_backup_id: str | None = None,
        source: FullBackupSource | None = None,
    ) -> dict[str, Any]:
        created_at = _now()
        doc: dict[str, Any] = {
            "id": uuid4().hex,
            "kind": kind,
            "label": label.strip() if label and label.strip() else None,
            "trigger": trigger,
            "summary": summary,
            # JSONB requires plain JSON types; column keeps the datetime.
            "created_at": created_at.isoformat(),
            "schema_version": SCHEMA_VERSION,
            "included_areas": list(included_areas or []),
            "change_label": (change_label or summary).strip(),
            "category": category or category_for_trigger(trigger),
            "payload": payload,
            "payload_type": payload_type,
        }
        if base_backup_id:
            doc["base_backup_id"] = base_backup_id
        if source:
            doc["source"] = source
        async with session_scope() as session:
            session.add(
                ConfigBackupRow(
                    id=doc["id"],
                    kind=kind,
                    created_at=created_at,
                    doc=doc,
                )
            )
        return _serialize_backup(doc)

    async def list_metadata(self, *, limit: int = 500) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = (
                select(ConfigBackupRow)
                .order_by(ConfigBackupRow.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            enriched: list[dict[str, Any]] = []
            for row in rows:
                serialized = _serialize_backup(dict(row.doc), include_payload=False)
                if not serialized.get("category"):
                    serialized["category"] = category_for_trigger(str(serialized.get("trigger") or ""))
                enriched.append(serialized)
            return enriched

    async def list_by_kind(self, kind: str, *, limit: int = 500) -> list[dict[str, Any]]:
        """List metadata for a normalized kind (includes legacy stored kinds)."""
        async with session_scope() as session:
            stmt = select(ConfigBackupRow)
            if kind == "change":
                stmt = stmt.where(_change_kind_filter())
            elif kind == "full":
                stmt = stmt.where(_full_kind_filter())
            else:
                stmt = stmt.where(ConfigBackupRow.kind == kind)
            stmt = stmt.order_by(ConfigBackupRow.created_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_serialize_backup(dict(row.doc), include_payload=False) for row in rows]

    async def list_timeline_metadata(
        self,
        *,
        page: int = 1,
        limit: int = 25,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return paginated timeline metadata newest-first."""
        async with session_scope() as session:
            total = int(
                (await session.execute(select(func.count()).select_from(ConfigBackupRow))).scalar_one()
            )
            skip = max(0, (page - 1) * limit)
            stmt = (
                select(ConfigBackupRow)
                .order_by(ConfigBackupRow.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            enriched: list[dict[str, Any]] = []
            for row in rows:
                serialized = _serialize_backup(dict(row.doc), include_payload=False)
                if not serialized.get("category"):
                    serialized["category"] = category_for_trigger(str(serialized.get("trigger") or ""))
                enriched.append(serialized)
            return enriched, total

    async def list_timeline_page(
        self,
        *,
        page: int = 1,
        limit: int = 25,
    ) -> dict[str, Any]:
        items, total = await self.list_timeline_metadata(page=page, limit=limit)
        safe_limit = max(1, limit)
        total_pages = max(1, (total + safe_limit - 1) // safe_limit) if total else 1
        return {
            "items": items,
            "page": max(1, page),
            "limit": safe_limit,
            "total": total,
            "total_pages": total_pages,
        }

    async def get_by_id(self, backup_id: str, *, include_payload: bool = True) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(ConfigBackupRow, backup_id)
            if not row:
                return None
            return _serialize_backup(dict(row.doc), include_payload=include_payload)

    async def delete_by_id(self, backup_id: str) -> bool:
        async with session_scope() as session:
            result = await session.execute(
                delete(ConfigBackupRow).where(ConfigBackupRow.id == backup_id)
            )
            return bool(result.rowcount)

    async def list_change_ids_oldest_first(self) -> list[str]:
        async with session_scope() as session:
            stmt = (
                select(ConfigBackupRow.id)
                .where(_change_kind_filter())
                .order_by(ConfigBackupRow.created_at.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [str(backup_id) for backup_id in rows if backup_id]

    async def list_full_ids_oldest_first(self) -> list[str]:
        async with session_scope() as session:
            stmt = (
                select(ConfigBackupRow.id)
                .where(_full_kind_filter())
                .order_by(ConfigBackupRow.created_at.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [str(backup_id) for backup_id in rows if backup_id]

    async def list_auto_ids_oldest_first(self) -> list[str]:
        """Legacy alias for change retention pruning."""
        return await self.list_change_ids_oldest_first()

    async def find_latest_full_before(
        self,
        when: datetime,
        *,
        include_payload: bool = False,
    ) -> dict[str, Any] | None:
        async with session_scope() as session:
            stmt = (
                select(ConfigBackupRow)
                .where(_full_kind_filter(), ConfigBackupRow.created_at <= when)
                .order_by(ConfigBackupRow.created_at.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if not row:
                return None
            return _serialize_backup(dict(row.doc), include_payload=include_payload)

    async def list_changes_since(
        self,
        since: datetime,
        *,
        include_payload: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return change entries with ``created_at >= since``, ascending."""
        async with session_scope() as session:
            stmt = (
                select(ConfigBackupRow)
                .where(_change_kind_filter(), ConfigBackupRow.created_at >= since)
                .order_by(ConfigBackupRow.created_at.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_serialize_backup(dict(row.doc), include_payload=include_payload) for row in rows]

    async def list_changes_between(
        self,
        start: datetime,
        end: datetime,
        *,
        include_payload: bool = True,
    ) -> list[dict[str, Any]]:
        """Return change entries with start < created_at <= end, ascending."""
        async with session_scope() as session:
            stmt = (
                select(ConfigBackupRow)
                .where(
                    _change_kind_filter(),
                    ConfigBackupRow.created_at > start,
                    ConfigBackupRow.created_at <= end,
                )
                .order_by(ConfigBackupRow.created_at.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_serialize_backup(dict(row.doc), include_payload=include_payload) for row in rows]
