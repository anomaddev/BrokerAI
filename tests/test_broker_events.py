from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import BrokerEventRow
from brokerai.db.repositories.broker_events import BrokerEventsRepository
from brokerai.trading.broker.models import BrokerEvent


pytestmark = pytest.mark.usefixtures("sqlite_db")


def _sample_event(event_id: str = "100") -> BrokerEvent:
    return BrokerEvent(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_event_id=event_id,
        event_type="ORDER_FILL",
        time=datetime(2026, 7, 2, 20, 27, 24, tzinfo=timezone.utc),
        broker_lot_id="565",
    )


@pytest.mark.asyncio
async def test_upsert_events_bulk_writes_in_chunks():
    repo = BrokerEventsRepository()
    count = await repo.upsert_events_bulk(
        [_sample_event("1"), _sample_event("2"), _sample_event("3")],
        batch_size=2,
    )

    assert count == 3
    async with session_scope() as session:
        row = (await session.execute(select(BrokerEventRow))).scalars().all()
    assert len(row) == 3


@pytest.mark.asyncio
async def test_upsert_events_delegates_to_bulk():
    repo = BrokerEventsRepository()
    with patch.object(repo, "upsert_events_bulk", new=AsyncMock(return_value=1)) as mock_bulk:
        result = await repo.upsert_events([_sample_event()])

    assert result == 1
    mock_bulk.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_event_doc_updates_existing_row():
    repo = BrokerEventsRepository()
    event = _sample_event()
    await repo.upsert_event(event)

    updated = _sample_event()
    updated.broker_lot_id = "566"
    await repo.upsert_event(updated)

    async with session_scope() as session:
        stored = (
            await session.execute(
                select(BrokerEventRow).where(
                    BrokerEventRow.broker_event_id == event.broker_event_id
                )
            )
        ).scalar_one()
        assert stored.doc["broker_lot_id"] == "566"


@pytest.mark.asyncio
async def test_list_events_filters_by_broker_lot_id():
    repo = BrokerEventsRepository()
    await repo.upsert_events(
        [
            _sample_event("1"),
            BrokerEvent(
                exchange_id="oanda",
                account_id="101-001-test",
                broker_event_id="2",
                event_type="ORDER_FILL",
                time=datetime(2026, 7, 2, 20, 28, 0, tzinfo=timezone.utc),
                broker_lot_id="999",
            ),
        ]
    )

    docs = await repo.list_events(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_lot_id="565",
    )

    assert len(docs) == 1
    assert docs[0]["broker_event_id"] == "1"
    assert docs[0]["broker_lot_id"] == "565"


@pytest.mark.asyncio
async def test_trade_linked_event_unsets_retention_expires_at():
    repo = BrokerEventsRepository()

    low_value = BrokerEvent(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_event_id="99",
        event_type="MARGIN_CALL",
        time=datetime(2026, 7, 2, 20, 27, 24, tzinfo=timezone.utc),
    )
    trade_linked = BrokerEvent(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_event_id="99",
        event_type="ORDER_FILL",
        time=datetime(2026, 7, 2, 20, 27, 24, tzinfo=timezone.utc),
        broker_lot_id="565",
    )

    await repo.upsert_event(low_value)
    await repo.upsert_event(trade_linked)

    async with session_scope() as session:
        stored = (
            await session.execute(
                select(BrokerEventRow).where(BrokerEventRow.broker_event_id == "99")
            )
        ).scalar_one()
        assert stored.retention_expires_at is None
        assert "retention_expires_at" not in stored.doc
