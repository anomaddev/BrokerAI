from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import UpdateOne

from brokerai.config.settings import get_settings
from brokerai.db.client import get_db
from brokerai.trading.broker.event_retention import classify_event_retention
from brokerai.trading.broker.models import BrokerEvent


def broker_event_from_doc(doc: dict[str, Any]) -> BrokerEvent:
    """Rehydrate a persisted broker event document into a ``BrokerEvent``."""
    time = doc.get("time")
    if isinstance(time, str):
        time = datetime.fromisoformat(time.replace("Z", "+00:00"))
    elif time is not None and not isinstance(time, datetime):
        time = None
    return BrokerEvent(
        exchange_id=str(doc.get("exchange_id") or ""),
        account_id=str(doc.get("account_id") or ""),
        broker_event_id=str(doc.get("broker_event_id") or ""),
        event_type=str(doc.get("event_type") or ""),
        time=time,
        batch_id=doc.get("batch_id"),
        request_id=doc.get("request_id"),
        broker_lot_id=doc.get("broker_lot_id"),
        broker_order_id=doc.get("broker_order_id"),
        instrument=doc.get("instrument"),
        qty=doc.get("qty"),
        price=doc.get("price"),
        pl=doc.get("pl"),
        reason=doc.get("reason"),
        raw=doc.get("raw"),
    )


def _event_to_doc(
    event: BrokerEvent,
    *,
    protected_event_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "exchange_id": event.exchange_id,
        "account_id": event.account_id,
        "broker_event_id": event.broker_event_id,
        "event_type": event.event_type,
        "time": event.time,
        "batch_id": event.batch_id,
        "request_id": event.request_id,
        "broker_lot_id": event.broker_lot_id,
        "broker_order_id": event.broker_order_id,
        "instrument": event.instrument,
        "qty": event.qty,
        "price": event.price,
        "pl": event.pl,
        "reason": event.reason,
        "raw": event.raw,
        "updated_at": now,
    }
    retention_expires_at = classify_event_retention(
        event,
        protected_event_ids=protected_event_ids,
    )
    if retention_expires_at is not None:
        doc["retention_expires_at"] = retention_expires_at
    return doc


class BrokerEventsRepository:
    COLLECTION = "broker_events"

    async def upsert_event(
        self,
        event: BrokerEvent,
        *,
        protected_event_ids: frozenset[str] | None = None,
    ) -> None:
        await self.upsert_events([event], protected_event_ids=protected_event_ids)

    async def upsert_events(
        self,
        events: list[BrokerEvent],
        *,
        protected_event_ids: frozenset[str] | None = None,
    ) -> int:
        if not events:
            return 0
        settings = get_settings()
        return await self.upsert_events_bulk(
            events,
            batch_size=settings.broker_events_bulk_batch_size,
            protected_event_ids=protected_event_ids,
        )

    async def upsert_events_bulk(
        self,
        events: list[BrokerEvent],
        *,
        batch_size: int = 500,
        protected_event_ids: frozenset[str] | None = None,
    ) -> int:
        """Bulk upsert broker events using ``bulk_write`` (idempotent)."""
        if not events:
            return 0

        handle = await get_db()
        collection = handle.db[self.COLLECTION]
        chunk_size = max(1, batch_size)
        total = 0

        for offset in range(0, len(events), chunk_size):
            chunk = events[offset : offset + chunk_size]
            operations: list[UpdateOne] = []
            for event in chunk:
                key = {
                    "exchange_id": event.exchange_id,
                    "account_id": event.account_id,
                    "broker_event_id": event.broker_event_id,
                }
                doc = _event_to_doc(event, protected_event_ids=protected_event_ids)
                update: dict[str, Any] = {
                    "$set": doc,
                    "$setOnInsert": {"created_at": doc["updated_at"]},
                }
                if "retention_expires_at" not in doc:
                    update["$unset"] = {"retention_expires_at": ""}
                operations.append(UpdateOne(key, update, upsert=True))
            if operations:
                await collection.bulk_write(operations, ordered=False)
                total += len(operations)

        return total

    async def list_events(
        self,
        *,
        exchange_id: str,
        account_id: str | None = None,
        broker_lot_id: str | None = None,
        event_types: set[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        handle = await get_db()
        query: dict[str, Any] = {"exchange_id": exchange_id}
        if account_id:
            query["account_id"] = account_id
        if broker_lot_id:
            query["broker_lot_id"] = broker_lot_id
        if event_types:
            query["event_type"] = {"$in": sorted(event_types)}
        cursor = (
            handle.db[self.COLLECTION]
            .find(query, {"_id": 0})
            .sort("time", -1)
            .limit(max(1, min(limit, 2000)))
        )
        return await cursor.to_list(length=limit)

    async def list_events_by_order_id(
        self,
        *,
        exchange_id: str,
        account_id: str,
        broker_order_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        handle = await get_db()
        cursor = (
            handle.db[self.COLLECTION]
            .find(
                {
                    "exchange_id": exchange_id,
                    "account_id": account_id,
                    "broker_order_id": broker_order_id,
                },
                {"_id": 0},
            )
            .sort("time", 1)
            .limit(max(1, min(limit, 200)))
        )
        return await cursor.to_list(length=limit)

    async def list_events_for_lot(
        self,
        *,
        exchange_id: str,
        account_id: str,
        broker_lot_id: str,
        event_types: set[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        return await self.list_events(
            exchange_id=exchange_id,
            account_id=account_id,
            broker_lot_id=broker_lot_id,
            event_types=event_types,
            limit=limit,
        )

    async def get_by_event_id(
        self,
        exchange_id: str,
        account_id: str,
        broker_event_id: str,
    ) -> dict[str, Any] | None:
        handle = await get_db()
        return await handle.db[self.COLLECTION].find_one(
            {
                "exchange_id": exchange_id,
                "account_id": account_id,
                "broker_event_id": broker_event_id,
            },
            {"_id": 0},
        )
