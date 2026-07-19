from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import AiModelRow
from brokerai.db.repositories.research_settings import ResearchSettingsRepository
from brokerai.provider_defaults import default_title, resolve_base_url


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 4:
        return "***"
    return f"***{api_key[-4:]}"


def source_model_name(doc: dict[str, Any] | None) -> str:
    """Preferred model id on an API source for search / legacy fallbacks."""
    if not doc:
        return ""
    for key in ("default_model_name", "model_name"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def bind_source_model(source: dict[str, Any], model_name: str | None = None) -> dict[str, Any]:
    """Return a shallow copy of an API source with the selected model_name applied."""
    bound = dict(source)
    chosen = (model_name or "").strip() or source_model_name(source)
    bound["model_name"] = chosen
    return bound


class AiModelsRepository:
    COLLECTION = "ai_models"

    async def list_all(self) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(AiModelRow).order_by(AiModelRow.created_at)
            rows = (await session.execute(stmt)).scalars().all()
            return [dict(row.doc) for row in rows]

    async def find_by_id(self, model_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(AiModelRow, model_id)
            return dict(row.doc) if row else None

    async def find_enabled_by_id(self, model_id: str) -> dict[str, Any] | None:
        doc = await self.find_by_id(model_id)
        if doc and doc.get("enabled"):
            return doc
        return None

    async def find_by_type(self, model_type: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            stmt = select(AiModelRow)
            rows = (await session.execute(stmt)).scalars().all()
            for row in rows:
                doc = dict(row.doc)
                if doc.get("type") == model_type:
                    return doc
        return None

    async def create(
        self,
        *,
        title: str,
        model_type: str,
        base_url: str | None = None,
        model_name: str | None = None,
        api_key: str | None = None,
        enabled: bool = True,
        default_model_name: str | None = None,
    ) -> dict[str, Any]:
        existing = await self.find_by_type(model_type)
        if existing:
            raise ValueError(f"A {model_type} API source already exists")

        resolved_base = resolve_base_url(model_type, base_url)
        cleaned_model = (model_name or "").strip()
        cleaned_default = (default_model_name or cleaned_model or "").strip()
        doc = {
            "id": uuid4().hex,
            "title": (title or "").strip() or default_title(model_type),
            "type": model_type,
            "base_url": resolved_base,
            "model_name": cleaned_model,
            "default_model_name": cleaned_default,
            "api_key": api_key or "",
            "enabled": enabled,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        async with session_scope() as session:
            session.add(
                AiModelRow(
                    id=doc["id"],
                    enabled=doc["enabled"],
                    created_at=doc["created_at"],
                    doc=doc,
                )
            )
        return doc

    async def update(
        self,
        model_id: str,
        *,
        title: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        default_model_name: str | None = None,
        api_key: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        existing = await self.find_by_id(model_id)
        if not existing:
            return None

        updates: dict[str, Any] = {}
        if title is not None:
            updates["title"] = title.strip() or default_title(str(existing.get("type") or ""))
        if base_url is not None:
            updates["base_url"] = resolve_base_url(str(existing.get("type") or ""), base_url)
        if model_name is not None:
            updates["model_name"] = model_name.strip()
        if default_model_name is not None:
            updates["default_model_name"] = default_model_name.strip()
        if api_key is not None:
            updates["api_key"] = api_key
        if enabled is not None:
            updates["enabled"] = enabled

        if not updates:
            return existing

        updates["updated_at"] = _now_iso()

        async with session_scope() as session:
            row = await session.get(AiModelRow, model_id)
            if not row:
                return None
            doc = dict(row.doc)
            doc.update(updates)
            row.doc = doc
            row.enabled = bool(doc.get("enabled", False))
        return await self.find_by_id(model_id)

    async def set_enabled(self, model_id: str, enabled: bool) -> dict[str, Any] | None:
        return await self.update(model_id, enabled=enabled)

    async def delete(self, model_id: str) -> bool:
        async with session_scope() as session:
            result = await session.execute(delete(AiModelRow).where(AiModelRow.id == model_id))
            return bool(result.rowcount)

    async def delete_with_cleanup(self, model_id: str) -> bool:
        deleted = await self.delete(model_id)
        if deleted:
            await ResearchSettingsRepository().remove_model_references(model_id)
            from brokerai.db.repositories.data_connections import DataConnectionsRepository

            await DataConnectionsRepository().delete_model_capabilities(model_id)
        return deleted

    async def dedupe_by_type(self) -> list[str]:
        """Keep one source per provider type; remap refs and delete duplicates.

        Preference: newest enabled source, else newest by created_at.
        Returns deleted source ids.
        """
        all_sources = await self.list_all()
        by_type: dict[str, list[dict[str, Any]]] = {}
        for doc in all_sources:
            provider = str(doc.get("type") or "")
            if not provider:
                continue
            by_type.setdefault(provider, []).append(doc)

        deleted_ids: list[str] = []
        settings_repo = ResearchSettingsRepository()
        from brokerai.db.repositories.data_connections import DataConnectionsRepository

        connections_repo = DataConnectionsRepository()

        for _provider, docs in by_type.items():
            if len(docs) <= 1:
                continue

            def _sort_key(item: dict[str, Any]) -> tuple[int, str]:
                return (1 if item.get("enabled") else 0, str(item.get("created_at") or ""))

            docs_sorted = sorted(docs, key=_sort_key, reverse=True)
            keep = docs_sorted[0]
            keep_id = str(keep["id"])
            for extra in docs_sorted[1:]:
                extra_id = str(extra["id"])
                await settings_repo.remap_model_references(extra_id, keep_id)
                await connections_repo.remap_model_capabilities(extra_id, keep_id)
                if await self.delete(extra_id):
                    deleted_ids.append(extra_id)

        return deleted_ids
