from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.trading.trade_sync import (
    BROKER_CLOSED_REASON,
    _parse_broker_open_time,
    broker_closed_trade_to_ledger_close,
    broker_trade_to_ledger_intent,
    sync_oanda_trades_to_ledger,
)


def test_parse_broker_open_time_handles_nanoseconds():
    parsed = _parse_broker_open_time("2026-06-30T12:00:00.123456789Z")
    assert parsed == datetime(2026, 6, 30, 12, 0, 0, 123456, tzinfo=timezone.utc)


def test_broker_trade_to_ledger_intent_short_units_are_negative():
    intent = broker_trade_to_ledger_intent(
        {
            "id": "broker-1",
            "pair": "EUR/USD",
            "direction": "short",
            "units": 500,
            "price": 1.10123,
            "open_time": "2026-06-30T12:00:00.000000000Z",
        }
    )
    assert intent["units"] == -500
    assert intent["broker_order_id"] == "broker-1"
    assert intent["strategy_id"] == "oanda-import"
    assert intent["metadata"]["source"] == "oanda_sync"


def test_broker_closed_trade_to_ledger_close_maps_fields():
    close_kwargs = broker_closed_trade_to_ledger_close(
        {
            "id": "broker-1",
            "exit_price": 1.105,
            "realized_pl": -2.5,
            "open_time": "2026-06-30T12:00:00.000000000Z",
            "close_time": "2026-06-30T14:30:00.000000000Z",
            "closed_at": datetime(2026, 6, 30, 14, 30, tzinfo=timezone.utc),
        }
    )
    assert close_kwargs["reason"] == BROKER_CLOSED_REASON
    assert close_kwargs["exit_price"] == 1.105
    assert close_kwargs["realized_pl"] == -2.5
    assert close_kwargs["metadata"]["broker_trade_id"] == "broker-1"


@pytest.mark.asyncio
async def test_sync_skips_when_oanda_unconfigured():
    with patch(
        "brokerai.trading.trade_sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "",
            "account_id": "",
            "environment": "practice",
        }

        result = await sync_oanda_trades_to_ledger()

    assert result["configured"] is False
    assert result["imported"] == 0


@pytest.mark.asyncio
async def test_sync_imports_unmatched_broker_trade():
    broker_trade = {
        "id": "broker-99",
        "pair": "EUR/USD",
        "direction": "long",
        "units": 1000,
        "price": 1.10123,
        "open_time": "2026-06-30T12:00:00.000000000Z",
    }
    with patch(
        "brokerai.trading.trade_sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls, patch(
        "brokerai.trading.trade_sync.get_broker_open_trades_snapshot",
        new=AsyncMock(return_value={"trades": [broker_trade], "open_trade_count": 1}),
    ), patch(
        "brokerai.trading.trade_sync.TradesRepository",
    ) as mock_repo_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "acct",
            "environment": "practice",
        }

        trades_repo = AsyncMock()
        mock_repo_cls.return_value = trades_repo
        trades_repo.list_open_trades.return_value = []
        trades_repo.get_open_by_broker_order_id.return_value = None
        trades_repo.create_open_trade.return_value = {
            "id": "ledger-new",
            "pair": "EUR/USD",
            "direction": "long",
            "units": 1000,
        }

        result = await sync_oanda_trades_to_ledger()

    assert result["imported"] == 1
    trades_repo.create_open_trade.assert_awaited_once()
    kwargs = trades_repo.create_open_trade.await_args.kwargs
    assert kwargs["broker_order_id"] == "broker-99"


@pytest.mark.asyncio
async def test_sync_is_idempotent_when_broker_order_id_exists():
    broker_trade = {
        "id": "broker-99",
        "pair": "EUR/USD",
        "direction": "long",
        "units": 1000,
        "price": 1.10123,
    }
    with patch(
        "brokerai.trading.trade_sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls, patch(
        "brokerai.trading.trade_sync.get_broker_open_trades_snapshot",
        new=AsyncMock(return_value={"trades": [broker_trade], "open_trade_count": 1}),
    ), patch(
        "brokerai.trading.trade_sync.TradesRepository",
    ) as mock_repo_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "acct",
            "environment": "practice",
        }

        trades_repo = AsyncMock()
        mock_repo_cls.return_value = trades_repo
        trades_repo.list_open_trades.return_value = []
        trades_repo.get_open_by_broker_order_id.return_value = {"id": "existing"}

        result = await sync_oanda_trades_to_ledger()

    assert result["imported"] == 0
    assert result["skipped"] == 1
    trades_repo.create_open_trade.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_backfills_broker_order_id_on_pair_direction_match():
    ledger_trade = {
        "id": "ledger-1",
        "pair": "EUR/USD",
        "direction": "long",
        "broker_order_id": None,
    }
    broker_trade = {
        "id": "broker-1",
        "pair": "EUR/USD",
        "direction": "long",
        "units": 1000,
        "price": 1.10123,
    }
    with patch(
        "brokerai.trading.trade_sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls, patch(
        "brokerai.trading.trade_sync.get_broker_open_trades_snapshot",
        new=AsyncMock(return_value={"trades": [broker_trade], "open_trade_count": 1}),
    ), patch(
        "brokerai.trading.trade_sync.TradesRepository",
    ) as mock_repo_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "acct",
            "environment": "practice",
        }

        trades_repo = AsyncMock()
        mock_repo_cls.return_value = trades_repo
        trades_repo.list_open_trades.return_value = [ledger_trade]

        result = await sync_oanda_trades_to_ledger()

    assert result["imported"] == 0
    assert result["updated"] == 1
    trades_repo.update_broker_order_id.assert_awaited_once_with("ledger-1", "broker-1")


@pytest.mark.asyncio
async def test_sync_closes_ledger_trade_closed_on_broker():
    ledger_trade = {
        "id": "ledger-1",
        "pair": "EUR/USD",
        "direction": "long",
        "broker_order_id": "broker-1",
    }
    broker_closed = {
        "id": "broker-1",
        "pair": "EUR/USD",
        "direction": "long",
        "exit_price": 1.105,
        "realized_pl": 12.34,
        "open_time": "2026-06-30T12:00:00.000000000Z",
        "close_time": "2026-06-30T14:30:00.000000000Z",
        "closed_at": datetime(2026, 6, 30, 14, 30, tzinfo=timezone.utc),
    }
    with patch(
        "brokerai.trading.trade_sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls, patch(
        "brokerai.trading.trade_sync.get_broker_open_trades_snapshot",
        new=AsyncMock(return_value={"trades": [], "open_trade_count": 0}),
    ), patch(
        "brokerai.trading.trade_sync.get_broker_trade",
        new=AsyncMock(return_value=broker_closed),
    ), patch(
        "brokerai.trading.trade_sync.TradesRepository",
    ) as mock_repo_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "acct",
            "environment": "practice",
        }

        trades_repo = AsyncMock()
        mock_repo_cls.return_value = trades_repo
        trades_repo.list_open_trades.return_value = [ledger_trade]

        result = await sync_oanda_trades_to_ledger()

    assert result["closed"] == 1
    trades_repo.close_trade.assert_awaited_once()
    kwargs = trades_repo.close_trade.await_args.kwargs
    assert kwargs["reason"] == BROKER_CLOSED_REASON
    assert kwargs["exit_price"] == 1.105
    assert kwargs["realized_pl"] == 12.34


@pytest.mark.asyncio
async def test_sync_backfills_closed_trade_missing_pl():
    closed_trade = {
        "id": "closed-ledger-1",
        "status": "closed",
        "broker_order_id": "broker-88",
        "close_metadata": {},
    }
    broker_closed = {
        "id": "broker-88",
        "exit_price": 1.105,
        "realized_pl": 4.2,
        "closed_at": datetime(2026, 6, 30, 14, 30, tzinfo=timezone.utc),
    }
    with patch(
        "brokerai.trading.trade_sync.ExchangeConnectionsRepository",
    ) as mock_exchange_cls, patch(
        "brokerai.trading.trade_sync.get_broker_open_trades_snapshot",
        new=AsyncMock(return_value={"trades": [], "open_trade_count": 0}),
    ), patch(
        "brokerai.trading.trade_sync.get_broker_trade",
        new=AsyncMock(return_value=broker_closed),
    ), patch(
        "brokerai.trading.trade_sync.TradesRepository",
    ) as mock_repo_cls:
        exchange_repo = AsyncMock()
        mock_exchange_cls.return_value = exchange_repo
        exchange_repo.get_oanda.return_value = {
            "access_token": "token",
            "account_id": "acct",
            "environment": "practice",
        }

        trades_repo = AsyncMock()
        mock_repo_cls.return_value = trades_repo
        trades_repo.list_open_trades.return_value = []
        trades_repo.list_closed_trades_missing_close_details.return_value = [closed_trade]
        trades_repo.backfill_close_details.return_value = True

        result = await sync_oanda_trades_to_ledger()

    assert result["backfilled"] == 1
    trades_repo.backfill_close_details.assert_awaited_once()
    kwargs = trades_repo.backfill_close_details.await_args.kwargs
    assert kwargs["realized_pl"] == 4.2
    assert kwargs["exit_price"] == 1.105
