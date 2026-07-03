from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.client import get_db
from brokerai.trading.broker.models import BrokerEvent


def _event_to_doc(event: BrokerEvent) -> dict[str, Any]:
    return {
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
        "updated_at": datetime.now(timezone.utc),
    }


class BrokerEventsRepository:
    COLLECTION = "broker_events"

    async def upsert_event(self, event: BrokerEvent) -> None:
        handle = await get_db()
        key = {
            "exchange_id": event.exchange_id,
            "account_id": event.account_id,
            "broker_event_id": event.broker_event_id,
        }
        doc = _event_to_doc(event)
        existing = await handle.db[self.COLLECTION].find_one(key, {"_id": 0})
        if existing:
            doc["created_at"] = existing.get("created_at", doc["updated_at"])
        else:
            doc["created_at"] = doc["updated_at"]
        await handle.db[self.COLLECTION].update_one(key, {"$set": doc}, upsert=True)

    async def upsert_events(self, events: list[BrokerEvent]) -> int:
        count = 0
        for event in events:
            await self.upsert_event(event)
            count += 1
        return count

    async def list_events(
        self,
        *,
        exchange_id: str,
        account_id: str | None = None,
        broker_lot_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        handle = await get_db()
        query: dict[str, Any] = {"exchange_id": exchange_id}
        if account_id:
            query["account_id"] = account_id
        if broker_lot_id:
            query["broker_lot_id"] = broker_lot_id
        cursor = (
            handle.db[self.COLLECTION]
            .find(query, {"_id": 0})
            .sort("time", -1)
            .limit(max(1, min(limit, 2000)))
        )
        return await cursor.to_list(length=limit)

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
