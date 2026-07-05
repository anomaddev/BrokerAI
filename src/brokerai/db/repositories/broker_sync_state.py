from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from brokerai.db.client import get_db


def _default_lock_holder() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class BrokerSyncStateRepository:
    COLLECTION = "broker_sync_state"

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
        """Acquire a distributed lease for OANDA account polling.

        Uses a conditional update only (never upsert on the lock filter). When no
        row exists yet, inserts one. If insert races another writer, retries the
        conditional update once.

        Edge cases:
        - Another process holds a non-expired lock → returns ``False`` (no error).
        - Row exists but fails the lock ``$or`` (held by another) → must not upsert;
          that would violate the unique ``(exchange_id, account_id)`` index.
        """
        handle = await get_db()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(30, ttl_seconds))
        lock_holder = holder or _default_lock_holder()

        lock_filter: dict[str, Any] = {
            "exchange_id": exchange_id,
            "account_id": account_id,
            "$or": [
                {"sync_lock_holder": {"$exists": False}},
                {"sync_lock_expires_at": {"$lte": now}},
                {"sync_lock_holder": lock_holder},
            ],
        }
        lock_set = {
            "sync_lock_holder": lock_holder,
            "sync_lock_expires_at": expires_at,
            "updated_at": now,
        }

        result = await handle.db[self.COLLECTION].update_one(
            lock_filter,
            {"$set": lock_set},
        )
        if result.modified_count:
            return True

        try:
            await handle.db[self.COLLECTION].insert_one(
                {
                    "exchange_id": exchange_id,
                    "account_id": account_id,
                    **lock_set,
                    "created_at": now,
                }
            )
            return True
        except DuplicateKeyError:
            result = await handle.db[self.COLLECTION].update_one(
                lock_filter,
                {"$set": lock_set},
            )
            return bool(result.modified_count)

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
