from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

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
        "broker_order_id": "123",
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
    stored: dict[str, dict] = {}

    async def insert_one(doc):
        stored[doc["id"]] = doc

    async def update_one(filter_doc, update_doc):
        trade_id = filter_doc["id"]
        if trade_id not in stored:
            return MagicMock(matched_count=0)
        stored[trade_id] = {**stored[trade_id], **update_doc["$set"]}
        return MagicMock(matched_count=1)

    cursor = MagicMock()

    async def to_list(length=200):
        rows = [row for row in stored.values() if row.get("status") == "open"]
        return rows[:length]

    cursor.to_list = AsyncMock(side_effect=to_list)
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor

    closed_cursor = MagicMock()

    async def closed_to_list(length=200):
        rows = [row for row in stored.values() if row.get("status") == "closed"]
        return rows[:length]

    closed_cursor.to_list = AsyncMock(side_effect=closed_to_list)
    closed_cursor.sort.return_value = closed_cursor
    closed_cursor.limit.return_value = closed_cursor

    def find(query, projection):
        if query.get("status") == "closed":
            return closed_cursor
        return cursor

    collection = MagicMock()
    collection.insert_one = AsyncMock(side_effect=insert_one)
    collection.update_one = AsyncMock(side_effect=update_one)
    collection.find_one = AsyncMock(
        side_effect=lambda query, projection: stored.get(query["id"])
    )
    collection.find = MagicMock(side_effect=find)
    db = MagicMock()
    db.__getitem__.return_value = collection
    handle = MagicMock()
    handle.db = db

    repo = TradesRepository()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("brokerai.db.repositories.trades.get_db", AsyncMock(return_value=handle))

        open_doc = await repo.create_open_trade(
            {
                "strategy_id": "s1",
                "strategy_name": "EMA",
                "pair": "EUR/USD",
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
        assert open_doc["status"] == "open"
        assert open_doc["metadata"]["analysis_run_id"] == "run-1"

        trade_id = open_doc["id"]
        await repo.close_trade(trade_id, reason="reverse_crossover")

        open_rows = await repo.list_trades(status="open", limit=10)
        assert open_rows == []

        closed_rows = await repo.list_trades(status="closed", limit=10)
        assert len(closed_rows) == 1
        assert closed_rows[0]["close_reason"] == "reverse_crossover"

        fetched = await repo.get_by_id(trade_id)
        assert fetched is not None
        assert fetched["status"] == "closed"


@pytest.mark.asyncio
async def test_list_trades_combined_orders_open_before_closed():
    open_rows = [
        {
            "id": "open-1",
            "status": "open",
            "opened_at": datetime(2026, 6, 30, 14, 0, tzinfo=timezone.utc),
        },
        {
            "id": "open-2",
            "status": "open",
            "opened_at": datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
        },
    ]
    closed_rows = [
        {
            "id": "closed-1",
            "status": "closed",
            "closed_at": datetime(2026, 6, 29, 16, 0, tzinfo=timezone.utc),
        }
    ]

    repo = TradesRepository()
    calls: list[dict] = []

    async def fake_list_trades(**kwargs):
        calls.append(kwargs)
        if kwargs.get("status") == "open":
            return [serialize_trade(row) for row in open_rows]
        return [serialize_trade(row) for row in closed_rows]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(repo, "list_trades", fake_list_trades)
        combined = await repo._list_trades_combined(limit=10)

    assert [trade["id"] for trade in combined] == ["open-1", "open-2", "closed-1"]
    assert calls[0]["status"] == "open"
    assert calls[1]["status"] == "closed"
    assert calls[1]["limit"] == 8
