from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from brokerai.config.settings import get_settings
from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import BrokerEventRow
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


def _row_values(doc: dict[str, Any]) -> dict[str, Any]:
    event_time = doc.get("time")
    if isinstance(event_time, str):
        event_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
    return {
        "exchange_id": doc["exchange_id"],
        "account_id": doc["account_id"],
        "broker_event_id": doc["broker_event_id"],
        "event_time": event_time,
        "retention_expires_at": doc.get("retention_expires_at"),
        "doc": doc,
    }


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
        """Bulk upsert broker events (idempotent)."""
        if not events:
            return 0

        chunk_size = max(1, batch_size)
        total = 0

        for offset in range(0, len(events), chunk_size):
            chunk = events[offset : offset + chunk_size]
            values: list[dict[str, Any]] = []
            for event in chunk:
                doc = _event_to_doc(event, protected_event_ids=protected_event_ids)
                doc.setdefault("created_at", doc["updated_at"])
                values.append(_row_values(doc))

            async with session_scope() as session:
                bind = session.get_bind()
                dialect = bind.dialect.name if bind is not None else "postgresql"

                if dialect == "postgresql":
                    stmt = pg_insert(BrokerEventRow).values(values)
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_broker_events_natural",
                        set_={
                            "event_time": stmt.excluded.event_time,
                            "retention_expires_at": stmt.excluded.retention_expires_at,
                            "doc": stmt.excluded.doc,
                        },
                    )
                    await session.execute(stmt)
                else:
                    for item in values:
                        stmt = select(BrokerEventRow).where(
                            BrokerEventRow.exchange_id == item["exchange_id"],
                            BrokerEventRow.account_id == item["account_id"],
                            BrokerEventRow.broker_event_id == item["broker_event_id"],
                        )
                        row = (await session.execute(stmt)).scalar_one_or_none()
                        if row is None:
                            session.add(BrokerEventRow(**item))
                        else:
                            row.event_time = item["event_time"]
                            row.retention_expires_at = item["retention_expires_at"]
                            row.doc = item["doc"]
                total += len(values)

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
        async with session_scope() as session:
            stmt = select(BrokerEventRow).where(BrokerEventRow.exchange_id == exchange_id)
            if account_id:
                stmt = stmt.where(BrokerEventRow.account_id == account_id)
            if broker_lot_id:
                stmt = stmt.where(
                    BrokerEventRow.doc["broker_lot_id"].as_string() == broker_lot_id
                )
            if event_types:
                stmt = stmt.where(
                    BrokerEventRow.doc["event_type"].as_string().in_(sorted(event_types))
                )
            stmt = stmt.order_by(BrokerEventRow.event_time.desc()).limit(
                max(1, min(limit, 2000))
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [dict(row.doc) for row in rows]

    async def list_events_by_order_id(
        self,
        *,
        exchange_id: str,
        account_id: str,
        broker_order_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = (
                select(BrokerEventRow)
                .where(
                    BrokerEventRow.exchange_id == exchange_id,
                    BrokerEventRow.account_id == account_id,
                    BrokerEventRow.doc["broker_order_id"].as_string() == broker_order_id,
                )
                .order_by(BrokerEventRow.event_time.asc())
                .limit(max(1, min(limit, 200)))
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [dict(row.doc) for row in rows]

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
        async with session_scope() as session:
            stmt = select(BrokerEventRow).where(
                BrokerEventRow.exchange_id == exchange_id,
                BrokerEventRow.account_id == account_id,
                BrokerEventRow.broker_event_id == broker_event_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return dict(row.doc) if row else None
