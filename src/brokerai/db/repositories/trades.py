from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from brokerai.db.client import get_db


class TradesRepository:
    COLLECTION = "trades"

    async def create_open_trade(
        self,
        intent: dict[str, Any],
        *,
        broker_order_id: str | None = None,
    ) -> dict[str, Any]:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        trade_id = uuid4().hex
        document = {
            "id": trade_id,
            "strategy_id": intent.get("strategy_id"),
            "strategy_name": intent.get("strategy_name"),
            "pair": intent.get("pair"),
            "asset_class": intent.get("asset_class", "forex"),
            "direction": intent.get("direction"),
            "entry_price": intent.get("entry_price"),
            "stop_loss": intent.get("stop_loss"),
            "take_profit": intent.get("take_profit"),
            "exit_mode": intent.get("exit_mode"),
            "risk_pct": intent.get("risk_pct"),
            "units": intent.get("units"),
            "confidence": intent.get("confidence"),
            "status": "open",
            "broker_order_id": broker_order_id,
            "metadata": intent.get("metadata") or {},
            "opened_at": now,
            "trade_date": now.date().isoformat(),
            "created_at": now,
            "updated_at": now,
        }
        await handle.db[self.COLLECTION].insert_one(document)
        return document

    async def close_trade(self, trade_id: str, *, reason: str, metadata: dict | None = None) -> None:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        await handle.db[self.COLLECTION].update_one(
            {"id": trade_id},
            {
                "$set": {
                    "status": "closed",
                    "closed_at": now,
                    "close_reason": reason,
                    "close_metadata": metadata or {},
                    "updated_at": now,
                }
            },
        )

    async def list_open_trades(self) -> list[dict[str, Any]]:
        handle = await get_db()
        cursor = handle.db[self.COLLECTION].find({"status": "open"}, {"_id": 0})
        return await cursor.to_list(length=500)

    async def count_trades_today(self, strategy_id: str, pair: str, *, on_date: date | None = None) -> int:
        handle = await get_db()
        day = (on_date or datetime.now(timezone.utc).date()).isoformat()
        return await handle.db[self.COLLECTION].count_documents(
            {
                "strategy_id": strategy_id,
                "pair": pair,
                "trade_date": day,
            }
        )

    async def daily_trade_counts(self, *, on_date: date | None = None) -> dict[tuple[str, str], int]:
        handle = await get_db()
        day = (on_date or datetime.now(timezone.utc).date()).isoformat()
        pipeline = [
            {"$match": {"trade_date": day}},
            {"$group": {"_id": {"strategy_id": "$strategy_id", "pair": "$pair"}, "count": {"$sum": 1}}},
        ]
        rows = await handle.db[self.COLLECTION].aggregate(pipeline).to_list(length=1000)
        return {
            (row["_id"]["strategy_id"], row["_id"]["pair"]): int(row["count"])
            for row in rows
        }
