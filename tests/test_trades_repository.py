from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.db.repositories.trades import TradesRepository, serialize_trade


def test_serialize_trade_formats_datetimes():
    doc = {
        "id": "trade-1",
        "strategy_id": "s1",
        "strategy_name": "EMA",
        "pair": "EUR/USD",
        "asset_class": "forex",
        "direction": "long",
        "entry_price": 1.1,
        "stop_loss": 1.09,
        "take_profit": 1.12,
        "exit_mode": "rr_ratio",
        "risk_pct": 1.0,
        "units": 1000,
        "confidence": 0.8,
        "status": "open",
        "state": "open",
        "broker_order_id": "123",
        "broker_lot_id": "123",
        "symbol": "EUR_USD",
        "metadata": {},
        "trade_date": "2026-06-30",
        "opened_at": datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        "closed_at": None,
        "created_at": datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
    }
    serialized = serialize_trade(doc)
    assert serialized["opened_at"] == "2026-06-30T12:00:00+00:00"
    assert serialized["closed_at"] is None


@pytest.mark.asyncio
async def test_trades_repository_list_and_get():
    lots_repo = AsyncMock()
    repo = TradesRepository()
    repo._lots = lots_repo

    open_doc = {
        "id": "trade-1",
        "status": "open",
        "state": "open",
        "metadata": {"analysis_run_id": "run-1"},
        "broker_lot_id": "broker-1",
    }
    closed_doc = {
        **open_doc,
        "status": "closed",
        "state": "closed",
        "close_reason": "reverse_crossover",
    }

    lots_repo.upsert_lot = AsyncMock(return_value=open_doc)
    lots_repo.list_lots = AsyncMock(side_effect=lambda **kwargs: (
        [open_doc] if kwargs.get("state") == "open" else [closed_doc] if kwargs.get("state") == "closed" else []
    ))
    lots_repo.get_by_id = AsyncMock(side_effect=[open_doc, closed_doc])
    lots_repo.close_lot = AsyncMock()

    created = await repo.create_open_trade(
        {
            "strategy_id": "s1",
            "strategy_name": "EMA",
            "pair": "EUR/USD",
            "asset_class": "forex",
            "direction": "long",
            "entry_price": 1.1,
            "stop_loss": 1.09,
            "take_profit": 1.12,
            "exit_mode": "rr_ratio",
            "risk_pct": 1.0,
            "confidence": 0.8,
            "metadata": {"analysis_run_id": "run-1"},
        },
        broker_order_id="broker-1",
    )
    assert created["status"] == "open"

    with patch("brokerai.trading.broker.state.BrokerStateService") as mock_state_cls:
        mock_state = AsyncMock()
        mock_state_cls.return_value = mock_state
        mock_state.close_lot = AsyncMock(return_value=closed_doc)
        await repo.close_trade("trade-1", reason="reverse_crossover")

    open_rows = await repo.list_trades(status="open", limit=10)
    assert open_rows == [open_doc]

    closed_rows = await repo.list_trades(status="closed", limit=10)
    assert closed_rows == [closed_doc]

    fetched = await repo.get_by_id("trade-1")
    assert fetched is not None
    assert fetched["status"] == "closed"


@pytest.mark.asyncio
async def test_list_trades_all_sorted_open_first_then_last_modified():
    rows = [
        {
            "id": "open-old",
            "status": "open",
            "opened_at": datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        },
        {
            "id": "open-new",
            "status": "open",
            "opened_at": datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        },
        {
            "id": "closed-newest",
            "status": "closed",
            "closed_at": datetime(2026, 7, 2, 8, 0, tzinfo=timezone.utc),
        },
    ]

    from brokerai.db.repositories.broker_lots import _sort_lots_for_display

    sorted_rows = _sort_lots_for_display(
        [serialize_trade(row) for row in rows],
        open_first=True,
    )
    assert [row["id"] for row in sorted_rows] == ["open-new", "open-old", "closed-newest"]


@pytest.mark.asyncio
async def test_list_trades_combined_delegates_to_list_lots():
    open_rows = [
        {
            "id": "open-1",
            "exchange_id": "oanda",
            "account_id": "a",
            "broker_lot_id": "1",
            "asset_class": "forex",
            "state": "open",
            "status": "open",
            "instrument": "EUR_USD",
            "symbol": "EUR_USD",
            "direction": "long",
            "initial_qty": 1,
            "current_qty": 1,
            "entry_price": 1.1,
            "opened_at": datetime(2026, 6, 30, 14, 0, tzinfo=timezone.utc),
        },
        {
            "id": "open-2",
            "exchange_id": "oanda",
            "account_id": "a",
            "broker_lot_id": "2",
            "asset_class": "forex",
            "state": "open",
            "status": "open",
            "instrument": "EUR_USD",
            "symbol": "EUR_USD",
            "direction": "long",
            "initial_qty": 1,
            "current_qty": 1,
            "entry_price": 1.1,
            "opened_at": datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        },
    ]
    closed_rows = [
        {
            "id": "closed-1",
            "exchange_id": "oanda",
            "account_id": "a",
            "broker_lot_id": "3",
            "asset_class": "forex",
            "state": "closed",
            "status": "closed",
            "instrument": "EUR_USD",
            "symbol": "EUR_USD",
            "direction": "long",
            "initial_qty": 1,
            "current_qty": 0,
            "entry_price": 1.1,
            "closed_at": datetime(2026, 6, 29, 16, 0, tzinfo=timezone.utc),
        }
    ]

    repo = TradesRepository()
    calls: list[dict] = []

    async def fake_list_lots(**kwargs):
        calls.append(kwargs)
        state = kwargs.get("state")
        if state == "all":
            return [serialize_trade(row) for row in open_rows] + [
                serialize_trade(row) for row in closed_rows
            ]
        if state == "open":
            return [serialize_trade(row) for row in open_rows]
        return [serialize_trade(row) for row in closed_rows]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(repo._lots, "list_lots", fake_list_lots)
        combined = await repo.list_trades(status="all", limit=10)

    assert [trade["id"] for trade in combined] == ["open-1", "open-2", "closed-1"]
    assert calls[0]["state"] == "all"
