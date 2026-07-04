from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.trading.broker.models import BrokerEvent, PositionLot, SyncResult
from brokerai.trading.broker.sync import run_broker_sync
from brokerai.trading.oanda_bootstrap import OandaBootstrapResult


@pytest.fixture(autouse=True)
def _reset_broker_sync_globals():
    import brokerai.trading.broker.sync as sync_module

    sync_module._LAST_SUCCESSFUL_SYNC = None
    yield
    sync_module._LAST_SUCCESSFUL_SYNC = None


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
async def test_run_broker_sync_bootstrap_upserts_lots_and_events():
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
    event = BrokerEvent(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_event_id="566",
        event_type="ORDER_FILL",
        time=datetime(2026, 7, 2, 20, 27, 24, tzinfo=timezone.utc),
        broker_lot_id="565",
    )
    bootstrap = OandaBootstrapResult(
        lots=[lot],
        events=[event],
        last_transaction_id="566",
        summary={"balance": "10000"},
        counts={"bootstrap_open_lots": 1, "bootstrap_events": 1},
    )

    with patch(
        "brokerai.trading.broker.sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls, patch(
        "brokerai.trading.broker.sync.run_oanda_bootstrap",
        new=AsyncMock(return_value=bootstrap),
    ), patch(
        "brokerai.trading.broker.sync.get_adapter",
    ) as mock_get_adapter, patch(
        "brokerai.trading.broker.sync.BrokerLotsRepository",
    ) as mock_lots_cls, patch(
        "brokerai.trading.broker.sync.BrokerEventsRepository",
    ) as mock_events_cls, patch(
        "brokerai.trading.broker.sync.BrokerSyncStateRepository",
    ) as mock_state_cls, patch(
        "brokerai.trading.broker.sync.persist_account_summary_snapshot",
        new=AsyncMock(return_value=True),
    ), patch(
        "brokerai.trading.broker.sync.repair_stale_cursor_if_needed",
        new=AsyncMock(return_value=(None, False, [])),
    ), patch(
        "brokerai.trading.broker.sync.InstrumentExposureRepository",
    ) as mock_exposure_cls, patch(
        "brokerai.trading.broker.sync.reconcile_local_open_against_broker",
        new=AsyncMock(return_value=0),
    ), patch(
        "brokerai.trading.broker.sync.reconcile_cancelled_lots",
        new=AsyncMock(return_value=0),
    ), patch(
        "brokerai.trading.broker.sync.backfill_closed_lot_details",
        new=AsyncMock(return_value=[]),
    ):
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "101-001-test",
            "environment": "practice",
        }

        adapter = AsyncMock()
        adapter.validate_exposure.return_value = []
        mock_get_adapter.return_value = adapter

        lots_repo = AsyncMock()
        mock_lots_cls.return_value = lots_repo
        lots_repo.list_closed_lots_missing_close_details.return_value = []
        lots_repo.list_open_lots.return_value = []

        exposure_repo = AsyncMock()
        mock_exposure_cls.return_value = exposure_repo
        exposure_repo.recompute_for_account = AsyncMock(return_value=0)

        events_repo = AsyncMock()
        mock_events_cls.return_value = events_repo
        events_repo.upsert_events.return_value = 1

        state_repo = AsyncMock()
        mock_state_cls.return_value = state_repo
        state_repo.get_cursor.return_value = None
        state_repo.get_state.return_value = None
        state_repo.needs_environment_reset.return_value = False
        state_repo.try_acquire_sync_lock.return_value = True

        result = await run_broker_sync(exchange_id="oanda", mode="full", force=True)

    assert result.configured is True
    assert result.lots_upserted == 1
    assert result.events_upserted == 1
    assert result.summary_synced is True
    assert result.cursor_after == "566"
    lots_repo.upsert_lot.assert_called()
    events_repo.upsert_events.assert_awaited()


@pytest.mark.asyncio
async def test_run_broker_sync_incremental_skips_exposure_when_recent():
    poll_result = type(
        "Poll",
        (),
        {
            "lots": [],
            "events": [],
            "live_open_lots": [],
            "cursor": "567",
            "repair_triggered": False,
            "poll_state": {},
        },
    )()

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
    ) as mock_state_cls, patch(
        "brokerai.trading.broker.sync.repair_stale_cursor_if_needed",
        new=AsyncMock(return_value=("566", False, [])),
    ), patch(
        "brokerai.trading.broker.sync._should_run_exposure_check",
        new=AsyncMock(return_value=False),
    ), patch(
        "brokerai.trading.broker.sync.reconcile_local_open_against_broker",
        new=AsyncMock(return_value=0),
    ), patch(
        "brokerai.trading.broker.sync.reconcile_cancelled_lots",
        new=AsyncMock(return_value=0),
    ), patch(
        "brokerai.trading.broker.sync.backfill_closed_lot_details",
        new=AsyncMock(return_value=[]),
    ), patch(
        "brokerai.trading.broker.sync.InstrumentExposureRepository",
    ) as mock_exposure_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "101-001-test",
            "environment": "practice",
        }

        adapter = AsyncMock()
        adapter.sync_incremental_from_changes = AsyncMock(return_value=poll_result)
        adapter.validate_exposure = AsyncMock(return_value=[])
        mock_get_adapter.return_value = adapter

        lots_repo = AsyncMock()
        mock_lots_cls.return_value = lots_repo
        lots_repo.list_closed_lots_missing_close_details.return_value = []
        lots_repo.list_open_lots.return_value = []

        exposure_repo = AsyncMock()
        mock_exposure_cls.return_value = exposure_repo
        exposure_repo.recompute_for_account = AsyncMock(return_value=0)

        events_repo = AsyncMock()
        mock_events_cls.return_value = events_repo
        events_repo.upsert_events.return_value = 0

        state_repo = AsyncMock()
        mock_state_cls.return_value = state_repo
        state_repo.get_cursor.return_value = "566"
        state_repo.get_state.return_value = {"account_bootstrap_at": datetime.now(timezone.utc)}
        state_repo.needs_environment_reset.return_value = False
        state_repo.try_acquire_sync_lock.return_value = True

        result = await run_broker_sync(exchange_id="oanda", mode="incremental", force=True)

    assert result.configured is True
    adapter.validate_exposure.assert_not_awaited()


@pytest.mark.asyncio
async def test_incremental_gap_repair_persists_events_once():
    poll_event = BrokerEvent(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_event_id="567",
        event_type="ORDER_FILL",
        time=datetime(2026, 7, 2, 21, 0, 0, tzinfo=timezone.utc),
        broker_lot_id="565",
    )
    gap_event = BrokerEvent(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_event_id="566",
        event_type="ORDER_FILL",
        time=datetime(2026, 7, 2, 20, 30, 0, tzinfo=timezone.utc),
        broker_lot_id="565",
    )
    poll_result = type(
        "Poll",
        (),
        {
            "lots": [],
            "events": [poll_event, gap_event],
            "live_open_lots": [],
            "cursor": "567",
            "repair_triggered": True,
            "poll_state": {},
        },
    )()

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
    ) as mock_state_cls, patch(
        "brokerai.trading.broker.sync.repair_stale_cursor_if_needed",
        new=AsyncMock(return_value=("565", False, [])),
    ), patch(
        "brokerai.trading.broker.sync._should_run_exposure_check",
        new=AsyncMock(return_value=False),
    ), patch(
        "brokerai.trading.broker.sync.reconcile_local_open_against_broker",
        new=AsyncMock(return_value=0),
    ), patch(
        "brokerai.trading.broker.sync.reconcile_cancelled_lots",
        new=AsyncMock(return_value=0),
    ), patch(
        "brokerai.trading.broker.sync.backfill_closed_lot_details",
        new=AsyncMock(return_value=[]),
    ), patch(
        "brokerai.trading.broker.sync.InstrumentExposureRepository",
    ) as mock_exposure_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "101-001-test",
            "environment": "practice",
        }

        adapter = AsyncMock()
        adapter.sync_incremental_from_changes = AsyncMock(return_value=poll_result)
        mock_get_adapter.return_value = adapter

        lots_repo = AsyncMock()
        mock_lots_cls.return_value = lots_repo
        lots_repo.list_closed_lots_missing_close_details.return_value = []
        lots_repo.list_open_lots.return_value = []

        exposure_repo = AsyncMock()
        mock_exposure_cls.return_value = exposure_repo
        exposure_repo.recompute_for_account = AsyncMock(return_value=0)

        events_repo = AsyncMock()
        mock_events_cls.return_value = events_repo
        events_repo.upsert_events.return_value = 2

        state_repo = AsyncMock()
        mock_state_cls.return_value = state_repo
        state_repo.get_cursor.return_value = "565"
        state_repo.get_state.return_value = {"account_bootstrap_at": datetime.now(timezone.utc)}
        state_repo.needs_environment_reset.return_value = False
        state_repo.try_acquire_sync_lock.return_value = True

        result = await run_broker_sync(exchange_id="oanda", mode="incremental", force=True)

    assert result.configured is True
    assert result.repair_triggered is True
    events_repo.upsert_events.assert_awaited_once()
    persisted = events_repo.upsert_events.await_args.args[0]
    assert {event.broker_event_id for event in persisted} == {"566", "567"}


@pytest.mark.asyncio
async def test_stale_repair_events_merged_into_persist_batch():
    poll_event = BrokerEvent(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_event_id="568",
        event_type="ORDER_FILL",
        time=datetime(2026, 7, 2, 22, 0, 0, tzinfo=timezone.utc),
        broker_lot_id="565",
    )
    stale_event = BrokerEvent(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_event_id="567",
        event_type="ORDER_FILL",
        time=datetime(2026, 7, 2, 21, 0, 0, tzinfo=timezone.utc),
        broker_lot_id="565",
    )
    poll_result = type(
        "Poll",
        (),
        {
            "lots": [],
            "events": [poll_event],
            "live_open_lots": [],
            "cursor": "568",
            "repair_triggered": False,
            "poll_state": {},
        },
    )()

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
    ) as mock_state_cls, patch(
        "brokerai.trading.broker.sync.repair_stale_cursor_if_needed",
        new=AsyncMock(return_value=("566", True, [stale_event])),
    ), patch(
        "brokerai.trading.broker.sync._should_run_exposure_check",
        new=AsyncMock(return_value=False),
    ), patch(
        "brokerai.trading.broker.sync.reconcile_local_open_against_broker",
        new=AsyncMock(return_value=0),
    ), patch(
        "brokerai.trading.broker.sync.reconcile_cancelled_lots",
        new=AsyncMock(return_value=0),
    ), patch(
        "brokerai.trading.broker.sync.backfill_closed_lot_details",
        new=AsyncMock(return_value=[]),
    ), patch(
        "brokerai.trading.broker.sync.InstrumentExposureRepository",
    ) as mock_exposure_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "101-001-test",
            "environment": "practice",
        }

        adapter = AsyncMock()
        adapter.sync_incremental_from_changes = AsyncMock(return_value=poll_result)
        mock_get_adapter.return_value = adapter

        lots_repo = AsyncMock()
        mock_lots_cls.return_value = lots_repo
        lots_repo.list_closed_lots_missing_close_details.return_value = []
        lots_repo.list_open_lots.return_value = []

        exposure_repo = AsyncMock()
        mock_exposure_cls.return_value = exposure_repo
        exposure_repo.recompute_for_account = AsyncMock(return_value=0)

        events_repo = AsyncMock()
        mock_events_cls.return_value = events_repo
        events_repo.upsert_events.return_value = 2

        state_repo = AsyncMock()
        mock_state_cls.return_value = state_repo
        state_repo.get_cursor.return_value = "566"
        state_repo.get_state.return_value = {"account_bootstrap_at": datetime.now(timezone.utc)}
        state_repo.needs_environment_reset.return_value = False
        state_repo.try_acquire_sync_lock.return_value = True

        result = await run_broker_sync(exchange_id="oanda", mode="incremental", force=True)

    assert result.configured is True
    assert result.repair_triggered is True
    events_repo.upsert_events.assert_awaited_once()
    persisted = events_repo.upsert_events.await_args.args[0]
    assert {event.broker_event_id for event in persisted} == {"567", "568"}


@pytest.mark.asyncio
async def test_run_broker_sync_bootstrap_streaming_upserts_during_bootstrap():
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
    streamed_event = BrokerEvent(
        exchange_id="oanda",
        account_id="101-001-test",
        broker_event_id="566",
        event_type="ORDER_FILL",
        time=datetime(2026, 7, 2, 20, 27, 24, tzinfo=timezone.utc),
        broker_lot_id="565",
    )

    async def fake_bootstrap(*_args, event_sink=None, **_kwargs):
        if event_sink is not None:
            await event_sink([streamed_event], frozenset())
        return OandaBootstrapResult(
            lots=[lot],
            events=[],
            last_transaction_id="566",
            summary={"balance": "10000"},
            counts={"bootstrap_open_lots": 1, "bootstrap_events": 1},
            events_streamed=True,
        )

    with patch(
        "brokerai.trading.broker.sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls, patch(
        "brokerai.trading.broker.sync.run_oanda_bootstrap",
        new=fake_bootstrap,
    ), patch(
        "brokerai.trading.broker.sync.get_adapter",
    ) as mock_get_adapter, patch(
        "brokerai.trading.broker.sync.BrokerLotsRepository",
    ) as mock_lots_cls, patch(
        "brokerai.trading.broker.sync.BrokerEventsRepository",
    ) as mock_events_cls, patch(
        "brokerai.trading.broker.sync.BrokerSyncStateRepository",
    ) as mock_state_cls, patch(
        "brokerai.trading.broker.sync.persist_account_summary_snapshot",
        new=AsyncMock(return_value=True),
    ), patch(
        "brokerai.trading.broker.sync.repair_stale_cursor_if_needed",
        new=AsyncMock(return_value=(None, False, [])),
    ), patch(
        "brokerai.trading.broker.sync.InstrumentExposureRepository",
    ) as mock_exposure_cls, patch(
        "brokerai.trading.broker.sync.reconcile_local_open_against_broker",
        new=AsyncMock(return_value=0),
    ), patch(
        "brokerai.trading.broker.sync.reconcile_cancelled_lots",
        new=AsyncMock(return_value=0),
    ), patch(
        "brokerai.trading.broker.sync.backfill_closed_lot_details",
        new=AsyncMock(return_value=[]),
    ):
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "101-001-test",
            "environment": "practice",
        }

        adapter = AsyncMock()
        adapter.validate_exposure.return_value = []
        mock_get_adapter.return_value = adapter

        lots_repo = AsyncMock()
        mock_lots_cls.return_value = lots_repo
        lots_repo.list_closed_lots_missing_close_details.return_value = []
        lots_repo.list_open_lots.return_value = []

        exposure_repo = AsyncMock()
        mock_exposure_cls.return_value = exposure_repo
        exposure_repo.recompute_for_account = AsyncMock(return_value=0)

        events_repo = AsyncMock()
        mock_events_cls.return_value = events_repo
        events_repo.upsert_events.return_value = 1
        events_repo.list_events_for_lot = AsyncMock(return_value=[])

        state_repo = AsyncMock()
        mock_state_cls.return_value = state_repo
        state_repo.get_cursor.return_value = None
        state_repo.get_state.return_value = None
        state_repo.needs_environment_reset.return_value = False
        state_repo.try_acquire_sync_lock.return_value = True

        result = await run_broker_sync(exchange_id="oanda", mode="full", force=True)

    assert result.configured is True
    assert result.events_upserted == 1
    events_repo.upsert_events.assert_awaited_once()
    streamed_batch = events_repo.upsert_events.await_args.args[0]
    assert streamed_batch[0].broker_event_id == "566"


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
