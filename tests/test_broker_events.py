from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo import UpdateOne

from brokerai.trading.broker.models import BrokerEvent


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
    from brokerai.db.repositories.broker_events import BrokerEventsRepository

    collection = MagicMock()
    collection.bulk_write = AsyncMock()
    db_handle = MagicMock()
    db_handle.db = {"broker_events": collection}

    with patch(
        "brokerai.db.repositories.broker_events.get_db",
        new=AsyncMock(return_value=db_handle),
    ):
        repo = BrokerEventsRepository()
        count = await repo.upsert_events_bulk(
            [_sample_event("1"), _sample_event("2"), _sample_event("3")],
            batch_size=2,
        )

    assert count == 3
    assert collection.bulk_write.await_count == 2
    first_ops = collection.bulk_write.await_args_list[0].args[0]
    assert len(first_ops) == 2
    assert all(isinstance(op, UpdateOne) for op in first_ops)


@pytest.mark.asyncio
async def test_upsert_events_delegates_to_bulk():
    from brokerai.db.repositories.broker_events import BrokerEventsRepository

    repo = BrokerEventsRepository()
    with patch.object(repo, "upsert_events_bulk", new=AsyncMock(return_value=1)) as mock_bulk:
        result = await repo.upsert_events([_sample_event()])

    assert result == 1
    mock_bulk.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_event_doc_uses_set_on_insert_for_created_at():
    from brokerai.db.repositories.broker_events import BrokerEventsRepository

    collection = MagicMock()
    collection.bulk_write = AsyncMock()
    db_handle = MagicMock()
    db_handle.db = {"broker_events": collection}

    with patch(
        "brokerai.db.repositories.broker_events.get_db",
        new=AsyncMock(return_value=db_handle),
    ):
        repo = BrokerEventsRepository()
        await repo.upsert_event(_sample_event())

    ops = collection.bulk_write.await_args.args[0]
    update_doc = ops[0]._doc
    assert "$setOnInsert" in update_doc
    assert "created_at" in update_doc["$setOnInsert"]


@pytest.mark.asyncio
async def test_trade_linked_event_unsets_retention_expires_at():
    from brokerai.db.repositories.broker_events import BrokerEventsRepository

    collection = MagicMock()
    collection.bulk_write = AsyncMock()
    db_handle = MagicMock()
    db_handle.db = {"broker_events": collection}

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

    with patch(
        "brokerai.db.repositories.broker_events.get_db",
        new=AsyncMock(return_value=db_handle),
    ):
        repo = BrokerEventsRepository()
        await repo.upsert_event(low_value)
        await repo.upsert_event(trade_linked)

    second_ops = collection.bulk_write.await_args_list[1].args[0]
    second_update = second_ops[0]._doc
    assert "retention_expires_at" not in second_update["$set"]
    assert second_update["$unset"] == {"retention_expires_at": ""}
