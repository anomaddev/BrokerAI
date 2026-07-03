from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.trading.broker.models import PositionLot
from brokerai.trading.broker.sync import run_broker_sync


@pytest.mark.asyncio
async def test_run_broker_sync_unconfigured():
    with patch(
        "brokerai.trading.broker.sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "",
            "account_id": "",
            "environment": "practice",
        }

        result = await run_broker_sync(exchange_id="oanda", mode="incremental", force=True)

    assert result.configured is False


@pytest.mark.asyncio
async def test_run_broker_sync_upserts_lots():
    lot = PositionLot(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_lot_id="565",
        asset_class="forex",
        state="open",
        instrument="EUR_JPY",
        symbol="EUR_JPY",
        direction="short",
        initial_qty=683,
        current_qty=683,
        entry_price=184.196,
    )

    with patch(
        "brokerai.trading.broker.sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls, patch(
        "brokerai.trading.broker.sync.get_adapter",
    ) as mock_get_adapter, patch(
        "brokerai.trading.broker.sync.BrokerLotsRepository",
    ) as mock_lots_cls, patch(
        "brokerai.trading.broker.sync.BrokerEventsRepository",
    ) as mock_events_cls, patch(
        "brokerai.trading.broker.sync.BrokerSyncStateRepository",
    ) as mock_state_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "101-001-test",
            "environment": "practice",
        }

        adapter = AsyncMock()
        adapter.sync_lots.return_value = ([lot], "567")
        adapter.fetch_open_lots_with_prices.return_value = [lot]
        adapter.sync_events.return_value = type(
            "R",
            (),
            {"events": [], "cursor": "567", "last_event_id": None},
        )()
        adapter.validate_exposure.return_value = []
        mock_get_adapter.return_value = adapter

        lots_repo = AsyncMock()
        mock_lots_cls.return_value = lots_repo
        lots_repo.list_open_lots.return_value = []
        lots_repo.list_closed_lots_missing_close_details.return_value = []

        events_repo = AsyncMock()
        mock_events_cls.return_value = events_repo
        events_repo.upsert_events.return_value = 0

        state_repo = AsyncMock()
        mock_state_cls.return_value = state_repo
        state_repo.get_cursor.return_value = None

        result = await run_broker_sync(exchange_id="oanda", mode="full", force=True)

    assert result.configured is True
    assert result.lots_upserted == 1
    lots_repo.upsert_lot.assert_called()


@pytest.mark.asyncio
async def test_backfill_closed_lot_details_uses_events_not_trade_api_for_txn_id():
    closed_at = datetime(2026, 6, 30, 14, 30, tzinfo=timezone.utc)
    with patch(
        "brokerai.trading.broker.sync.BrokerLotsRepository",
    ) as mock_lots_cls, patch(
        "brokerai.trading.broker.sync.BrokerEventsRepository",
    ) as mock_events_cls, patch(
        "brokerai.integrations.oanda.get_broker_trade",
        new=AsyncMock(),
    ) as mock_get_trade:
        from brokerai.trading.broker.sync import backfill_closed_lot_details

        lots_repo = AsyncMock()
        mock_lots_cls.return_value = lots_repo
        lots_repo.list_closed_lots_missing_close_details.return_value = [
            {
                "id": "lot-523",
                "account_id": "101-001-test",
                "broker_lot_id": "523",
                "closing_event_ids": [],
            }
        ]
        lots_repo.backfill_close_details.return_value = True

        events_repo = AsyncMock()
        mock_events_cls.return_value = events_repo
        events_repo.list_events.return_value = []
        events_repo.get_by_event_id.return_value = {
            "broker_event_id": "523",
            "broker_lot_id": "434",
            "event_type": "ORDER_FILL",
            "price": 184.5,
            "pl": 12.3,
            "time": closed_at,
        }

        backfilled = await backfill_closed_lot_details(
            exchange_id="oanda",
            account_id="101-001-test",
            credentials={"access_token": "token", "environment": "practice"},
        )

    assert backfilled == ["lot-523"]
    mock_get_trade.assert_not_called()
    kwargs = lots_repo.backfill_close_details.await_args.kwargs
    assert kwargs["exit_price"] == 184.5
    assert kwargs["realized_pl"] == 12.3
