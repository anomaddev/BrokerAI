from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from brokerai.db.client import get_db

DEFAULT_WATCH_MAX_AGE_SECONDS = 300


class CandleWatchRepository:
    COLLECTION = "candle_watch"

    async def upsert_watch(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        requester: str,
        *,
        bar_count: int,
    ) -> None:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        await handle.db[self.COLLECTION].update_one(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "source": source,
                "requester": requester,
            },
            {
                "$set": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "source": source,
                    "requester": requester,
                    "bar_count": max(1, bar_count),
                    "updated_at": now,
                }
            },
            upsert=True,
        )

    async def touch_watch(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        requester: str,
    ) -> None:
        handle = await get_db()
        now = datetime.now(timezone.utc)
        await handle.db[self.COLLECTION].update_one(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "source": source,
                "requester": requester,
            },
            {"$set": {"updated_at": now}},
        )

    async def list_active_watches(
        self,
        *,
        source: str | None = None,
        max_age_seconds: int = DEFAULT_WATCH_MAX_AGE_SECONDS,
    ) -> list[dict[str, Any]]:
        handle = await get_db()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, max_age_seconds))
        query: dict[str, Any] = {"updated_at": {"$gte": cutoff}}
        if source is not None:
            query["source"] = source
        cursor = handle.db[self.COLLECTION].find(query, {"_id": 0})
        return await cursor.to_list(length=500)
