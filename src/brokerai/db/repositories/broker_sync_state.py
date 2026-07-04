from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

from brokerai.db.client import get_db


def _default_lock_holder() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class BrokerSyncStateRepository:
    COLLECTION = "broker_sync_state"

    @staticmethod
    def _as_utc_aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    async def get_state(self, exchange_id: str, account_id: str) -> dict[str, Any] | None:
        handle = await get_db()
        return await handle.db[self.COLLECTION].find_one(
            {"exchange_id": exchange_id, "account_id": account_id},
            {"_id": 0},
        )

    async def get_cursor(self, exchange_id: str, account_id: str) -> str | None:
        doc = await self.get_state(exchange_id, account_id)
        if doc is None:
            return None
        cursor = doc.get("sync_cursor")
        return str(cursor) if cursor else None

    async def get_last_sync_at(self, exchange_id: str, account_id: str) -> datetime | None:
        doc = await self.get_state(exchange_id, account_id)
        if doc is None:
            return None
        return doc.get("last_sync_at")

    async def reset_state(self, exchange_id: str, account_id: str) -> None:
        """Clear sync cursor and bootstrap markers (account/credential switch)."""
        handle = await get_db()
        now = datetime.now(timezone.utc)
        await handle.db[self.COLLECTION].update_one(
            {"exchange_id": exchange_id, "account_id": account_id},
            {
                "$set": {"updated_at": now},
                "$unset": {
                    "sync_cursor": "",
                    "account_bootstrap_at": "",
                    "last_sync_error": "",
                },
            },
            upsert=True,
        )

    async def try_acquire_sync_lock(
        self,
        exchange_id: str,
        account_id: str,
        *,
        holder: str | None = None,
        ttl_seconds: int = 90,
    ) -> bool:
        """Acquire a distributed lease for OANDA account polling."""
        handle = await get_db()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(30, ttl_seconds))
        lock_holder = holder or _default_lock_holder()

        doc = await handle.db[self.COLLECTION].find_one(
            {"exchange_id": exchange_id, "account_id": account_id},
            {"_id": 0, "sync_lock_holder": 1, "sync_lock_expires_at": 1},
        )
        if doc:
            existing_holder = doc.get("sync_lock_holder")
            existing_expires = self._as_utc_aware(doc.get("sync_lock_expires_at"))
            if (
                existing_holder
                and existing_holder != lock_holder
                and existing_expires is not None
                and existing_expires > now
            ):
                return False

        result = await handle.db[self.COLLECTION].update_one(
            {
                "exchange_id": exchange_id,
                "account_id": account_id,
                "$or": [
                    {"sync_lock_holder": {"$exists": False}},
                    {"sync_lock_expires_at": {"$lte": now}},
                    {"sync_lock_holder": lock_holder},
                ],
            },
            {
                "$set": {
                    "sync_lock_holder": lock_holder,
                    "sync_lock_expires_at": expires_at,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        if result.modified_count or result.upserted_id:
            return True
        # Re-check after race
        doc = await handle.db[self.COLLECTION].find_one(
            {"exchange_id": exchange_id, "account_id": account_id},
            {"_id": 0, "sync_lock_holder": 1},
        )
        return bool(doc and doc.get("sync_lock_holder") == lock_holder)

    async def release_sync_lock(
        self,
        exchange_id: str,
        account_id: str,
        *,
        holder: str | None = None,
    ) -> None:
        handle = await get_db()
        lock_holder = holder or _default_lock_holder()
        await handle.db[self.COLLECTION].update_one(
            {"exchange_id": exchange_id, "account_id": account_id, "sync_lock_holder": lock_holder},
            {
                "$unset": {"sync_lock_holder": "", "sync_lock_expires_at": ""},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )

    async def set_state(
        self,
        exchange_id: str,
        account_id: str,
        *,
        sync_cursor: str | None = None,
        last_sync_at: datetime | None = None,
        environment: str | None = None,
        account_bootstrap_at: datetime | None = None,
        last_sync_error: str | None = None,
        clear_last_sync_error: bool = False,
        last_exposure_check_at: datetime | None = None,
    ) -> None:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        updates: dict[str, Any] = {"updated_at": now, "last_sync_at": last_sync_at or now}
        if sync_cursor is not None:
            updates["sync_cursor"] = sync_cursor
        if environment is not None:
            updates["environment"] = environment
        if account_bootstrap_at is not None:
            updates["account_bootstrap_at"] = account_bootstrap_at
        if last_exposure_check_at is not None:
            updates["last_exposure_check_at"] = last_exposure_check_at
        if last_sync_error is not None:
            updates["last_sync_error"] = last_sync_error
        unset: dict[str, str] = {}
        if clear_last_sync_error:
            unset["last_sync_error"] = ""
        update_op: dict[str, Any] = {"$set": updates, "$setOnInsert": {"created_at": now}}
        if unset:
            update_op["$unset"] = unset
        await handle.db[self.COLLECTION].update_one(
            {"exchange_id": exchange_id, "account_id": account_id},
            update_op,
            upsert=True,
        )

    async def needs_environment_reset(
        self,
        exchange_id: str,
        account_id: str,
        *,
        environment: str,
    ) -> bool:
        doc = await self.get_state(exchange_id, account_id)
        if doc is None:
            return False
        stored_env = str(doc.get("environment") or "")
        return bool(stored_env and stored_env != environment)
