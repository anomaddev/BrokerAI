from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.db.repositories.broker_events import BrokerEventsRepository
from brokerai.trading.broker.cancelled_orders import find_order_cancellation
from brokerai.trading.broker.models import BrokerEvent
from brokerai.trading.broker.reconciliation import reconcile_cancelled_lots


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
async def test_find_order_cancellation_from_batch_cancel():
    cancel_time = datetime(2026, 7, 1, 7, 23, 50, tzinfo=timezone.utc)

    reject_types = {
        "MARKET_ORDER_REJECT",
        "LIMIT_ORDER_REJECT",
        "STOP_ORDER_REJECT",
    }

    async def fake_find_event_doc(
        exchange_id: str,
        *,
        account_id: str | None,
        filters: dict,
    ):
        event_type_in = filters.get("event_type_in")
        if event_type_in and reject_types.intersection(event_type_in):
            return None
        if filters.get("broker_event_id") == "484" and event_type_in:
            return {
                "broker_event_id": "484",
                "event_type": "MARKET_ORDER",
                "batch_id": "484",
                "time": cancel_time,
            }
        if filters.get("batch_id") == "484" and filters.get("event_type") == "ORDER_CANCEL":
            return {
                "reason": "STOP_LOSS_ON_FILL_LOSS",
                "time": cancel_time,
                "event_type": "ORDER_CANCEL",
            }
        return None

    with (
        patch(
            "brokerai.trading.broker.cancelled_orders.BrokerEventsRepository.list_events_by_order_id",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "brokerai.trading.broker.cancelled_orders._find_event_doc",
            new=fake_find_event_doc,
        ),
    ):
        result = await find_order_cancellation("oanda", "484", account_id="acct")

    assert result is not None
    assert result["reason"] == "STOP_LOSS_ON_FILL_LOSS"


@pytest.mark.asyncio
async def test_reconcile_cancelled_lots_marks_phantom_rows():
    from brokerai.db.pg.client import session_scope
    from brokerai.db.pg.models import BrokerLotRow

    cancel_time = datetime(2026, 7, 1, 7, 23, 50, tzinfo=timezone.utc)
    async with session_scope() as session:
        session.add(
            BrokerLotRow(
                id="lot-484",
                exchange_id="oanda",
                account_id="",
                broker_lot_id="484",
                state="open",
                doc={
                    "id": "lot-484",
                    "broker_lot_id": "484",
                    "account_id": "",
                    "raw_broker": None,
                    "state": "open",
                },
            )
        )

    lots_repo = AsyncMock()
    with patch(
        "brokerai.trading.broker.cancelled_orders.find_order_cancellation",
        new=AsyncMock(
            return_value={"reason": "STOP_LOSS_ON_FILL_LOSS", "cancelled_at": cancel_time},
        ),
    ):
        marked = await reconcile_cancelled_lots(lots_repo, exchange_id="oanda", account_id="acct")

    assert marked == 1
    lots_repo.cancel_lot.assert_called_once_with(
        "lot-484",
        reason="STOP_LOSS_ON_FILL_LOSS",
        cancelled_at=cancel_time,
    )


def test_serialize_lot_cancelled_status():
    from brokerai.db.repositories.broker_lots import serialize_lot

    payload = serialize_lot(
        {
            "id": "lot-1",
            "state": "cancelled",
            "status": "cancelled",
            "close_reason": "STOP_LOSS_ON_FILL_LOSS",
            "pair": "CAD/JPY",
            "direction": "long",
            "initial_qty": 1333,
            "current_qty": 0,
            "entry_price": 114.528,
            "broker_lot_id": "484",
            "exchange_id": "oanda",
            "account_id": "",
            "asset_class": "forex",
        }
    )
    assert payload["state"] == "cancelled"
    assert payload["reason_display"]["short"] == "SL on fill"
