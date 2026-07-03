from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_find_order_cancellation_from_batch_cancel():
    from brokerai.trading.broker.cancelled_orders import find_order_cancellation

    handle = MagicMock()
    cancel = {
        "event_type": "ORDER_CANCEL",
        "broker_order_id": "484",
        "batch_id": "484",
        "reason": "STOP_LOSS_ON_FILL_LOSS",
        "time": datetime(2026, 7, 1, 7, 23, 50, tzinfo=timezone.utc),
    }
    handle.db.broker_events.find_one = AsyncMock(side_effect=[None, cancel])

    with patch("brokerai.trading.broker.cancelled_orders.get_db", new=AsyncMock(return_value=handle)):
        result = await find_order_cancellation("oanda", "484", account_id="acct")

    assert result is not None
    assert result["reason"] == "STOP_LOSS_ON_FILL_LOSS"


@pytest.mark.asyncio
async def test_reconcile_cancelled_lots_marks_phantom_rows():
    from brokerai.trading.broker.reconciliation import reconcile_cancelled_lots

    lots_repo = AsyncMock()
    lot = {
        "id": "lot-484",
        "broker_lot_id": "484",
        "account_id": "",
        "raw_broker": None,
    }
    handle = MagicMock()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[lot])
    handle.db.broker_lots.find.return_value = cursor

    cancel_time = datetime(2026, 7, 1, 7, 23, 50, tzinfo=timezone.utc)
    with patch("brokerai.db.client.get_db", new=AsyncMock(return_value=handle)), patch(
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
    assert payload["status"] == "cancelled"
    assert payload["reason_display"]["short"] == "SL on fill"
