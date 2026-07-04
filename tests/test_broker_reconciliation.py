from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from brokerai.db.repositories.broker_lots import _dedupe_open_lots, serialize_lot
from brokerai.trading.broker.models import PositionLot
from brokerai.trading.broker.reconciliation import reconcile_local_open_against_broker


@pytest.mark.asyncio
async def test_reconcile_closes_stale_local_not_on_broker():
    lots_repo = AsyncMock()
    lots_repo.list_open_lots.side_effect = [
        [
            {
                "id": "local-1",
                "broker_lot_id": "565",
                "pair": "EUR/JPY",
                "direction": "short",
                "state": "open",
                "initial_qty": 100,
                "current_qty": 100,
            },
            {
                "id": "local-2",
                "broker_lot_id": "999",
                "pair": "USD/JPY",
                "direction": "long",
                "state": "open",
                "initial_qty": 100,
                "current_qty": 100,
            },
        ],
        [
            {
                "id": "local-1",
                "broker_lot_id": "565",
                "pair": "EUR/JPY",
                "direction": "short",
                "state": "open",
                "initial_qty": 100,
                "current_qty": 100,
            },
        ],
        [],
    ]
    live = [
        PositionLot(
            exchange_id="oanda",
            account_id="acct",
            broker_lot_id="565",
            asset_class="forex",
            state="open",
            instrument="EUR_JPY",
            symbol="EUR_JPY",
            direction="short",
            initial_qty=100,
            current_qty=100,
            entry_price=1.0,
        )
    ]

    closed = await reconcile_local_open_against_broker(
        lots_repo,
        exchange_id="oanda",
        live_open_lots=live,
    )

    assert closed == 1
    lots_repo.close_lot.assert_awaited_once_with("local-2", reason="broker_closed")


@pytest.mark.asyncio
async def test_reconcile_closes_duplicate_locals_for_same_broker_trade():
    lots_repo = AsyncMock()
    opened = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    lots_repo.list_open_lots.side_effect = [
        [
            {
                "id": "dup-old",
                "broker_lot_id": "565",
                "pair": "EUR/JPY",
                "direction": "short",
                "state": "open",
                "open_time": opened,
                "initial_qty": 100,
                "current_qty": 100,
            },
            {
                "id": "dup-new",
                "broker_lot_id": "565",
                "pair": "EUR/JPY",
                "direction": "short",
                "state": "open",
                "open_time": datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
                "initial_qty": 100,
                "current_qty": 100,
            },
        ],
        [
            {
                "id": "dup-new",
                "broker_lot_id": "565",
                "pair": "EUR/JPY",
                "direction": "short",
                "state": "open",
                "open_time": datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
                "initial_qty": 100,
                "current_qty": 100,
            },
        ],
        [],
    ]
    live = [
        PositionLot(
            exchange_id="oanda",
            account_id="acct",
            broker_lot_id="565",
            asset_class="forex",
            state="open",
            instrument="EUR_JPY",
            symbol="EUR_JPY",
            direction="short",
            initial_qty=100,
            current_qty=100,
            entry_price=1.0,
        )
    ]

    closed = await reconcile_local_open_against_broker(
        lots_repo,
        exchange_id="oanda",
        live_open_lots=live,
    )

    assert closed == 1
    lots_repo.close_lot.assert_awaited_once_with("dup-old", reason="broker_closed")


def test_dedupe_open_lots_keeps_newest():
    rows = [
        serialize_lot(
            {
                "id": "a",
                "broker_lot_id": "565",
                "state": "open",
                "open_time": datetime(2026, 7, 1, tzinfo=timezone.utc),
                "initial_qty": 1,
                "current_qty": 1,
                "direction": "long",
                "entry_price": 1.0,
            }
        ),
        serialize_lot(
            {
                "id": "b",
                "broker_lot_id": "565",
                "state": "open",
                "open_time": datetime(2026, 7, 2, tzinfo=timezone.utc),
                "initial_qty": 1,
                "current_qty": 1,
                "direction": "long",
                "entry_price": 1.0,
            }
        ),
    ]
    deduped = _dedupe_open_lots(rows)
    assert len(deduped) == 1
    assert deduped[0]["id"] == "b"
