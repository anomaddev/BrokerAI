from __future__ import annotations

from typing import Any

from brokerai.db.repositories.singleton import get_singleton_doc, upsert_singleton_doc
from brokerai.provider_capabilities import (
    available_capabilities,
    capability_label,
    supports_capability,
)
from brokerai.db.client import get_db

SINGLETON_ID = "default"


class DataConnectionsRepository:
    COLLECTION = "data_connections"

    async def _get_api_key_connection(self, connection_type: str) -> dict[str, Any]:
        return await get_singleton_doc(
            self.COLLECTION,
            match={"type": connection_type},
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
            self.COLLECTION,
            match={"type": connection_type},
            document=doc,
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
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            {"type": "model", "model_id": model_id},
            {"_id": 0},
        )
        if not doc:
            return {}
        raw = doc.get("capabilities") or {}
        return {key: bool(value) for key, value in raw.items() if isinstance(key, str)}

    async def get_model_capabilities_map(self) -> dict[str, dict[str, bool]]:
        handle = await get_db()
        cursor = handle.db[self.COLLECTION].find({"type": "model"}, {"_id": 0})
        docs = await cursor.to_list(length=200)
        result: dict[str, dict[str, bool]] = {}
        for doc in docs:
            model_id = doc.get("model_id")
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
        handle = await get_db()
        await handle.db[self.COLLECTION].update_one(
            {"type": "model", "model_id": model_id},
            {
                "$set": {
                    "type": "model",
                    "model_id": model_id,
                    "provider_type": provider_type,
                    "capabilities": stored,
                }
            },
            upsert=True,
        )
        return stored

    async def delete_model_capabilities(self, model_id: str) -> None:
        handle = await get_db()
        await handle.db[self.COLLECTION].delete_one({"type": "model", "model_id": model_id})

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
            "model_name": model.get("model_name"),
            "enabled": bool(model.get("enabled")),
            "api_key_set": bool(model.get("api_key")),
            "available_capabilities": available,
            "capability_labels": {cap: capability_label(cap) for cap in available},
            "capabilities": {cap: bool(capabilities.get(cap)) for cap in available},
        }
