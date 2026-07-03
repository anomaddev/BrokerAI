from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.client import get_db
from brokerai.db.repositories.exchange_connections import OANDA_ID

SUMMARY_FIELDS = (
    "id",
    "alias",
    "currency",
    "balance",
    "nav",
    "unrealized_pl",
    "realized_pl",
    "margin_available",
    "margin_used",
    "open_trade_count",
    "open_position_count",
    "pending_order_count",
)


class OandaAccountSnapshotsRepository:
    """Persist OANDA account lists and time-series account summary snapshots."""

    ACCOUNTS_COLLECTION = "oanda_accounts_snapshots"
    SUMMARIES_COLLECTION = "oanda_account_summaries"

    async def upsert_accounts_snapshot(
        self,
        *,
        exchange_id: str = OANDA_ID,
        environment: str,
        accounts: list[dict[str, Any]],
        synced_at: datetime | None = None,
    ) -> None:
        """Store the latest accessible OANDA account list for *exchange_id*."""
        handle = await get_db()
        now = synced_at or datetime.now(timezone.utc)
        doc = {
            "exchange_id": exchange_id,
            "environment": environment,
            "accounts": accounts,
            "synced_at": now,
            "updated_at": now,
        }
        await handle.db[self.ACCOUNTS_COLLECTION].update_one(
            {"exchange_id": exchange_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    async def get_latest_accounts(self, *, exchange_id: str = OANDA_ID) -> dict[str, Any] | None:
        """Return the most recently synced OANDA account list document."""
        handle = await get_db()
        return await handle.db[self.ACCOUNTS_COLLECTION].find_one(
            {"exchange_id": exchange_id},
            {"_id": 0},
        )

    async def insert_summary_snapshot(
        self,
        *,
        exchange_id: str = OANDA_ID,
        account_id: str,
        environment: str,
        summary: dict[str, Any],
        synced_at: datetime | None = None,
    ) -> None:
        """Append one account summary snapshot for charting over time."""
        handle = await get_db()
        now = synced_at or datetime.now(timezone.utc)
        doc: dict[str, Any] = {
            "exchange_id": exchange_id,
            "account_id": account_id,
            "environment": environment,
            "synced_at": now,
        }
        for field in SUMMARY_FIELDS:
            if field in summary:
                doc[field] = summary[field]
        await handle.db[self.SUMMARIES_COLLECTION].insert_one(doc)

    async def get_latest_summary(
        self,
        *,
        exchange_id: str = OANDA_ID,
        account_id: str,
    ) -> dict[str, Any] | None:
        """Return the newest summary snapshot for *account_id*."""
        handle = await get_db()
        return await handle.db[self.SUMMARIES_COLLECTION].find_one(
            {"exchange_id": exchange_id, "account_id": account_id},
            {"_id": 0},
            sort=[("synced_at", -1)],
        )

    async def list_summary_history(
        self,
        *,
        exchange_id: str = OANDA_ID,
        account_id: str,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        """Return summary snapshots oldest-first for charting."""
        handle = await get_db()
        query: dict[str, Any] = {
            "exchange_id": exchange_id,
            "account_id": account_id,
        }
        synced_at: dict[str, Any] = {}
        if since is not None:
            synced_at["$gte"] = since
        if until is not None:
            synced_at["$lte"] = until
        if synced_at:
            query["synced_at"] = synced_at

        cursor = (
            handle.db[self.SUMMARIES_COLLECTION]
            .find(query, {"_id": 0})
            .sort("synced_at", 1)
            .limit(max(1, min(limit, 10_000)))
        )
        return await cursor.to_list(length=limit)

    @staticmethod
    def public_summary(doc: dict[str, Any]) -> dict[str, Any]:
        """Shape a stored summary document for API responses."""
        synced_at = doc.get("synced_at")
        payload: dict[str, Any] = {
            field: doc.get(field) for field in SUMMARY_FIELDS
        }
        payload["synced_at"] = synced_at.isoformat() if isinstance(synced_at, datetime) else synced_at
        payload["account_id"] = doc.get("account_id")
        payload["environment"] = doc.get("environment")
        return payload
