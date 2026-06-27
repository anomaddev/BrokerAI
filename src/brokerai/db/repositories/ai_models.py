from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from brokerai.db.client import get_db
from brokerai.db.repositories.research_settings import ResearchSettingsRepository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 4:
        return "***"
    return f"***{api_key[-4:]}"


class AiModelsRepository:
    COLLECTION = "ai_models"

    async def list_all(self) -> list[dict[str, Any]]:
        handle = await get_db()
        cursor = handle.db[self.COLLECTION].find({}, {"_id": 0}).sort("created_at", 1)
        return await cursor.to_list(length=100)

    async def find_by_id(self, model_id: str) -> dict[str, Any] | None:
        handle = await get_db()
        return await handle.db[self.COLLECTION].find_one({"id": model_id}, {"_id": 0})

    async def find_enabled_by_id(self, model_id: str) -> dict[str, Any] | None:
        doc = await self.find_by_id(model_id)
        if doc and doc.get("enabled"):
            return doc
        return None

    async def create(
        self,
        *,
        title: str,
        model_type: str,
        base_url: str,
        model_name: str,
        api_key: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        doc = {
            "id": uuid4().hex,
            "title": title.strip(),
            "type": model_type,
            "base_url": base_url.rstrip("/"),
            "model_name": model_name.strip(),
            "api_key": api_key or "",
            "enabled": enabled,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        handle = await get_db()
        await handle.db[self.COLLECTION].insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def update(
        self,
        model_id: str,
        *,
        title: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        existing = await self.find_by_id(model_id)
        if not existing:
            return None

        updates: dict[str, Any] = {}
        if title is not None:
            updates["title"] = title.strip()
        if base_url is not None:
            updates["base_url"] = base_url.rstrip("/")
        if model_name is not None:
            updates["model_name"] = model_name.strip()
        if api_key is not None:
            updates["api_key"] = api_key
        if enabled is not None:
            updates["enabled"] = enabled

        if not updates:
            return existing

        updates["updated_at"] = _now_iso()

        handle = await get_db()
        await handle.db[self.COLLECTION].update_one({"id": model_id}, {"$set": updates})
        return await self.find_by_id(model_id)

    async def set_enabled(self, model_id: str, enabled: bool) -> dict[str, Any] | None:
        return await self.update(model_id, enabled=enabled)

    async def delete(self, model_id: str) -> bool:
        handle = await get_db()
        result = await handle.db[self.COLLECTION].delete_one({"id": model_id})
        return result.deleted_count > 0

    async def delete_with_cleanup(self, model_id: str) -> bool:
        deleted = await self.delete(model_id)
        if deleted:
            await ResearchSettingsRepository().remove_model_references(model_id)
            from brokerai.db.repositories.data_connections import DataConnectionsRepository

            await DataConnectionsRepository().delete_model_capabilities(model_id)
        return deleted
