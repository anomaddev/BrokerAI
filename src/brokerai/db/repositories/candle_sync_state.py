from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.client import get_db
from pymongo import UpdateOne


class CandleSyncStateRepository:
    COLLECTION = "candle_sync_state"

    async def upsert_state(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        *,
        high_water_time: str | None = None,
        expected_latest: str | None = None,
        last_error: str | None = None,
    ) -> None:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        update: dict[str, Any] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": source,
            "last_sync_at": now,
        }
        if high_water_time is not None:
            update["high_water_time"] = high_water_time
        if expected_latest is not None:
            update["expected_latest_at_check"] = expected_latest
        if last_error is not None:
            update["last_error"] = last_error
        else:
            update["last_error"] = None

        await handle.db[self.COLLECTION].update_one(
            {"symbol": symbol, "timeframe": timeframe, "source": source},
            {"$set": update},
            upsert=True,
        )

    async def get_state(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> dict[str, Any] | None:
        handle = await get_db()
        return await handle.db[self.COLLECTION].find_one(
            {"symbol": symbol, "timeframe": timeframe, "source": source},
            {"_id": 0},
        )

    async def list_states(self, *, source: str | None = None) -> list[dict[str, Any]]:
        handle = await get_db()
        query: dict[str, Any] = {}
        if source is not None:
            query["source"] = source
        cursor = handle.db[self.COLLECTION].find(query, {"_id": 0})
        return await cursor.to_list(length=None)
