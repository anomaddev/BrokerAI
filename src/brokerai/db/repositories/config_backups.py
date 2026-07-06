from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from brokerai.db.client import get_db
from brokerai.config_backup.categories import category_for_trigger

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


def _strip_id(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc:
        return None
    return {key: value for key, value in doc.items() if key != "_id"}


def _format_created_at_api(value: object) -> str:
    """Serialize backup timestamps as explicit UTC ISO-8601 for the dashboard."""
    parsed = parse_created_at(value)
    if parsed is None:
        return str(value or "")
    as_utc = parsed.astimezone(timezone.utc)
    text = as_utc.isoformat(timespec="milliseconds")
    return text.replace("+00:00", "Z")


def _serialize_backup(doc: dict[str, Any], *, include_payload: bool = True) -> dict[str, Any]:
    serialized = _strip_id(doc) or {}
    created_at = serialized.get("created_at")
    if created_at is not None:
        serialized["created_at"] = _format_created_at_api(created_at)
    if not include_payload:
        serialized.pop("payload", None)
    return normalize_backup_metadata(serialized)


class ConfigBackupsRepository:
    COLLECTION = "config_backups"

    async def count(self) -> int:
        handle = await get_db()
        return await handle.db[self.COLLECTION].count_documents({})

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
        doc: dict[str, Any] = {
            "id": uuid4().hex,
            "kind": kind,
            "label": label.strip() if label and label.strip() else None,
            "trigger": trigger,
            "summary": summary,
            "created_at": _now(),
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
        handle = await get_db()
        await handle.db[self.COLLECTION].insert_one(doc)
        return _serialize_backup(doc)

    async def list_metadata(self, *, limit: int = 500) -> list[dict[str, Any]]:
        handle = await get_db()
        cursor = (
            handle.db[self.COLLECTION]
            .find({}, {"_id": 0, "payload": 0})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        enriched: list[dict[str, Any]] = []
        for doc in docs:
            serialized = _serialize_backup(doc, include_payload=False)
            if not serialized.get("category"):
                serialized["category"] = category_for_trigger(str(serialized.get("trigger") or ""))
            enriched.append(serialized)
        return enriched

    async def list_by_kind(self, kind: str, *, limit: int = 500) -> list[dict[str, Any]]:
        """List metadata for a normalized kind (includes legacy stored kinds)."""
        if kind == "change":
            query = {"kind": {"$in": ["change", "auto"]}}
        elif kind == "full":
            query = {"kind": {"$in": ["full", "manual"]}}
        else:
            query = {"kind": kind}

        handle = await get_db()
        cursor = (
            handle.db[self.COLLECTION]
            .find(query, {"_id": 0, "payload": 0})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_serialize_backup(doc, include_payload=False) for doc in docs]

    async def list_timeline_metadata(
        self,
        *,
        page: int = 1,
        limit: int = 25,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return paginated timeline metadata newest-first."""
        handle = await get_db()
        total = await handle.db[self.COLLECTION].count_documents({})
        skip = max(0, (page - 1) * limit)
        cursor = (
            handle.db[self.COLLECTION]
            .find({}, {"_id": 0, "payload": 0})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        enriched: list[dict[str, Any]] = []
        for doc in docs:
            serialized = _serialize_backup(doc, include_payload=False)
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
        handle = await get_db()
        projection = {"_id": 0}
        if not include_payload:
            projection["payload"] = 0
        doc = await handle.db[self.COLLECTION].find_one({"id": backup_id}, projection)
        if not doc:
            return None
        return _serialize_backup(doc, include_payload=include_payload)

    async def delete_by_id(self, backup_id: str) -> bool:
        handle = await get_db()
        result = await handle.db[self.COLLECTION].delete_one({"id": backup_id})
        return result.deleted_count > 0

    async def list_change_ids_oldest_first(self) -> list[str]:
        handle = await get_db()
        cursor = (
            handle.db[self.COLLECTION]
            .find({"kind": {"$in": ["change", "auto"]}}, {"_id": 0, "id": 1})
            .sort("created_at", 1)
        )
        docs = await cursor.to_list(length=10_000)
        return [str(doc["id"]) for doc in docs if doc.get("id")]

    async def list_full_ids_oldest_first(self) -> list[str]:
        handle = await get_db()
        cursor = (
            handle.db[self.COLLECTION]
            .find({"kind": {"$in": ["full", "manual"]}}, {"_id": 0, "id": 1})
            .sort("created_at", 1)
        )
        docs = await cursor.to_list(length=10_000)
        return [str(doc["id"]) for doc in docs if doc.get("id")]

    async def list_auto_ids_oldest_first(self) -> list[str]:
        """Legacy alias for change retention pruning."""
        return await self.list_change_ids_oldest_first()

    async def find_latest_full_before(
        self,
        when: datetime,
        *,
        include_payload: bool = False,
    ) -> dict[str, Any] | None:
        handle = await get_db()
        projection: dict[str, int] = {"_id": 0}
        if not include_payload:
            projection["payload"] = 0
        doc = await handle.db[self.COLLECTION].find_one(
            {
                "kind": {"$in": ["full", "manual"]},
                "created_at": {"$lte": when},
            },
            projection,
            sort=[("created_at", -1)],
        )
        if not doc:
            return None
        return _serialize_backup(doc, include_payload=include_payload)

    async def list_changes_since(
        self,
        since: datetime,
        *,
        include_payload: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return change entries with ``created_at >= since``, ascending."""
        handle = await get_db()
        projection: dict[str, int] = {"_id": 0}
        if not include_payload:
            projection["payload"] = 0
        cursor = (
            handle.db[self.COLLECTION]
            .find(
                {
                    "kind": {"$in": ["change", "auto"]},
                    "created_at": {"$gte": since},
                },
                projection,
            )
            .sort("created_at", 1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_serialize_backup(doc, include_payload=include_payload) for doc in docs]

    async def list_changes_between(
        self,
        start: datetime,
        end: datetime,
        *,
        include_payload: bool = True,
    ) -> list[dict[str, Any]]:
        """Return change entries with start < created_at <= end, ascending."""
        handle = await get_db()
        projection: dict[str, int] = {"_id": 0}
        if not include_payload:
            projection["payload"] = 0
        cursor = (
            handle.db[self.COLLECTION]
            .find(
                {
                    "kind": {"$in": ["change", "auto"]},
                    "created_at": {"$gt": start, "$lte": end},
                },
                projection,
            )
            .sort("created_at", 1)
        )
        docs = await cursor.to_list(length=10_000)
        return [_serialize_backup(doc, include_payload=include_payload) for doc in docs]
