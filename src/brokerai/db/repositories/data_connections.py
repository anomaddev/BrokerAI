from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import DataConnectionRow
from brokerai.db.repositories.singleton import get_singleton_doc, upsert_singleton_doc
from brokerai.provider_capabilities import (
    available_capabilities,
    capability_label,
    supports_capability,
)

SINGLETON_ID = "default"


class DataConnectionsRepository:
    COLLECTION = "data_connections"

    @staticmethod
    def _api_key_match(connection_type: str) -> dict[str, Any]:
        return {"conn_type": connection_type, "model_id": None}

    async def _get_api_key_connection(self, connection_type: str) -> dict[str, Any]:
        return await get_singleton_doc(
            DataConnectionRow,
            match=self._api_key_match(connection_type),
            defaults={
                "id": SINGLETON_ID,
                "type": connection_type,
                "api_key": "",
                "enabled": False,
            },
        )

    async def _save_api_key_connection(
        self,
        connection_type: str,
        *,
        api_key: str,
        enabled: bool,
    ) -> dict[str, Any]:
        doc = {
            "id": SINGLETON_ID,
            "type": connection_type,
            "api_key": api_key.strip(),
            "enabled": enabled,
        }
        return await upsert_singleton_doc(
            DataConnectionRow,
            match=self._api_key_match(connection_type),
            document=doc,
            denormalized={"conn_type": connection_type, "model_id": None},
        )

    async def get_newsapi(self) -> dict[str, Any]:
        return await self._get_api_key_connection("newsapi")

    async def save_newsapi(self, *, api_key: str, enabled: bool) -> dict[str, Any]:
        return await self._save_api_key_connection("newsapi", api_key=api_key, enabled=enabled)

    async def delete_newsapi(self) -> dict[str, Any]:
        return await self.save_newsapi(api_key="", enabled=False)

    async def get_massive(self) -> dict[str, Any]:
        return await self._get_api_key_connection("massive")

    async def save_massive(self, *, api_key: str, enabled: bool) -> dict[str, Any]:
        return await self._save_api_key_connection("massive", api_key=api_key, enabled=enabled)

    async def delete_massive(self) -> dict[str, Any]:
        return await self.save_massive(api_key="", enabled=False)

    async def get_model_capabilities(self, model_id: str) -> dict[str, bool]:
        async with session_scope() as session:
            stmt = select(DataConnectionRow).where(
                DataConnectionRow.conn_type == "model",
                DataConnectionRow.model_id == model_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if not row:
                return {}
            raw = dict(row.doc).get("capabilities") or {}
            return {key: bool(value) for key, value in raw.items() if isinstance(key, str)}

    async def get_model_capabilities_map(self) -> dict[str, dict[str, bool]]:
        async with session_scope() as session:
            stmt = select(DataConnectionRow).where(DataConnectionRow.conn_type == "model")
            rows = (await session.execute(stmt)).scalars().all()
            result: dict[str, dict[str, bool]] = {}
            for row in rows:
                doc = dict(row.doc)
                model_id = doc.get("model_id") or row.model_id
                if not model_id:
                    continue
                raw = doc.get("capabilities") or {}
                result[str(model_id)] = {
                    key: bool(value) for key, value in raw.items() if isinstance(key, str)
                }
            return result

    async def save_model_capabilities(
        self,
        model_id: str,
        *,
        provider_type: str,
        capabilities: dict[str, bool],
    ) -> dict[str, bool]:
        allowed = set(available_capabilities(provider_type))
        stored = {
            key: bool(value)
            for key, value in capabilities.items()
            if key in allowed and supports_capability(provider_type, key)
        }
        doc = {
            "type": "model",
            "model_id": model_id,
            "provider_type": provider_type,
            "capabilities": stored,
        }
        async with session_scope() as session:
            stmt = select(DataConnectionRow).where(
                DataConnectionRow.conn_type == "model",
                DataConnectionRow.model_id == model_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                session.add(
                    DataConnectionRow(
                        conn_type="model",
                        model_id=model_id,
                        doc=doc,
                    )
                )
            else:
                row.doc = doc
        return stored

    async def delete_model_capabilities(self, model_id: str) -> None:
        async with session_scope() as session:
            await session.execute(
                delete(DataConnectionRow).where(
                    DataConnectionRow.conn_type == "model",
                    DataConnectionRow.model_id == model_id,
                )
            )

    async def remap_model_capabilities(self, from_id: str, to_id: str) -> None:
        """Move capability rows from one API source id to another (merge on conflict)."""
        if from_id == to_id:
            return
        async with session_scope() as session:
            stmt = select(DataConnectionRow).where(
                DataConnectionRow.conn_type == "model",
                DataConnectionRow.model_id == from_id,
            )
            source_row = (await session.execute(stmt)).scalar_one_or_none()
            if source_row is None:
                return

            dest_stmt = select(DataConnectionRow).where(
                DataConnectionRow.conn_type == "model",
                DataConnectionRow.model_id == to_id,
            )
            dest_row = (await session.execute(dest_stmt)).scalar_one_or_none()
            source_doc = dict(source_row.doc)
            if dest_row is None:
                source_doc["model_id"] = to_id
                source_row.model_id = to_id
                source_row.doc = source_doc
                return

            dest_caps = dict((dest_row.doc or {}).get("capabilities") or {})
            source_caps = dict(source_doc.get("capabilities") or {})
            merged = {**source_caps, **dest_caps}
            dest_doc = dict(dest_row.doc)
            dest_doc["model_id"] = to_id
            dest_doc["capabilities"] = merged
            if source_doc.get("provider_type") and not dest_doc.get("provider_type"):
                dest_doc["provider_type"] = source_doc.get("provider_type")
            dest_row.doc = dest_doc
            await session.execute(
                delete(DataConnectionRow).where(
                    DataConnectionRow.conn_type == "model",
                    DataConnectionRow.model_id == from_id,
                )
            )

    @staticmethod
    def public_model_connection(
        model: dict[str, Any],
        capabilities: dict[str, bool],
    ) -> dict[str, Any]:
        provider_type = str(model.get("type") or "")
        available = available_capabilities(provider_type)
        return {
            "model_id": model.get("id"),
            "title": model.get("title"),
            "provider_type": provider_type,
            "model_name": model.get("default_model_name") or model.get("model_name") or "",
            "enabled": bool(model.get("enabled")),
            "api_key_set": bool(model.get("api_key")),
            "available_capabilities": available,
            "capability_labels": {cap: capability_label(cap) for cap in available},
            "capabilities": {cap: bool(capabilities.get(cap)) for cap in available},
        }
