from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.client import get_db


class BrokerSyncStateRepository:
    COLLECTION = "broker_sync_state"

    async def get_cursor(self, exchange_id: str, account_id: str) -> str | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            {"exchange_id": exchange_id, "account_id": account_id},
            {"_id": 0},
        )
        if doc is None:
            return None
        cursor = doc.get("sync_cursor")
        return str(cursor) if cursor else None

    async def get_last_sync_at(self, exchange_id: str, account_id: str) -> datetime | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            {"exchange_id": exchange_id, "account_id": account_id},
            {"_id": 0},
        )
        if doc is None:
            return None
        return doc.get("last_sync_at")

    async def set_state(
        self,
        exchange_id: str,
        account_id: str,
        *,
        sync_cursor: str | None = None,
        last_sync_at: datetime | None = None,
    ) -> None:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        updates: dict[str, Any] = {"updated_at": now, "last_sync_at": last_sync_at or now}
        if sync_cursor is not None:
            updates["sync_cursor"] = sync_cursor
        await handle.db[self.COLLECTION].update_one(
            {"exchange_id": exchange_id, "account_id": account_id},
            {"$set": updates, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
