from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.client import get_db
from pymongo import UpdateOne


class MarketDataRepository:
    COLLECTION = "market_data"

    async def upsert_candles(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        candles: list[dict[str, Any]],
        *,
        expires_at: datetime | None = None,
    ) -> int:
        """Upsert individual OHLCV candles keyed by symbol/timeframe/source/time."""
        if not candles:
            return 0

        handle = await get_db()
        now = datetime.now(timezone.utc)
        operations: list[UpdateOne] = []

        for candle in candles:
            candle_time = candle.get("time")
            if not candle_time:
                continue

            document: dict[str, Any] = {
                "symbol": symbol,
                "timeframe": timeframe,
                "source": source,
                "time": candle_time,
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"],
                "volume": candle.get("volume", 0),
                "fetched_at": now,
            }
            if candle.get("sessions") is not None:
                document["sessions"] = candle["sessions"]
            if candle.get("trading_day_et") is not None:
                document["trading_day_et"] = candle["trading_day_et"]
            if expires_at is not None:
                document["expires_at"] = expires_at

            operations.append(
                UpdateOne(
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "source": source,
                        "time": candle_time,
                    },
                    {"$set": document},
                    upsert=True,
                )
            )

        if not operations:
            return 0

        await handle.db[self.COLLECTION].bulk_write(operations, ordered=False)
        return len(operations)

    async def latest_candle_time(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> str | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            {"symbol": symbol, "timeframe": timeframe, "source": source},
            {"_id": 0, "time": 1},
            sort=[("time", -1)],
        )
        if not doc:
            return None
        value = doc.get("time")
        return str(value) if value else None

    async def earliest_candle_time(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> str | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            {"symbol": symbol, "timeframe": timeframe, "source": source},
            {"_id": 0, "time": 1},
            sort=[("time", 1)],
        )
        if not doc:
            return None
        value = doc.get("time")
        return str(value) if value else None

    async def find_candles(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
        ascending: bool = True,
        sessions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return individual cached candles, optionally bounded by open time."""
        handle = await get_db()
        query: dict[str, Any] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": source,
        }
        time_filter: dict[str, Any] = {}
        if since is not None:
            time_filter["$gte"] = since
        if until is not None:
            time_filter["$lte"] = until
        if time_filter:
            query["time"] = time_filter
        if sessions:
            query["sessions"] = {"$in": sessions}

        cursor = handle.db[self.COLLECTION].find(query, {"_id": 0}).sort(
            "time",
            1 if ascending else -1,
        )
        if limit is not None:
            cursor = cursor.limit(max(1, limit))

        return await cursor.to_list(length=limit or 5000)

    async def find_candles_after(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        after: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return candles strictly after *after* in ascending time order."""
        handle = await get_db()
        cursor = (
            handle.db[self.COLLECTION]
            .find(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "source": source,
                    "time": {"$gt": after},
                },
                {"_id": 0},
            )
            .sort("time", 1)
            .limit(max(1, limit))
        )
        return await cursor.to_list(length=max(1, limit))

    async def find_latest_candles(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        *,
        limit: int,
        since: str | None = None,
        until: str | None = None,
        sessions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the most recent *limit* candles in ascending time order."""
        rows = await self.find_candles(
            symbol,
            timeframe,
            source,
            since=since,
            until=until,
            limit=limit,
            ascending=False,
            sessions=sessions,
        )
        rows.reverse()
        return rows

    async def find_candle_times(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        *,
        since: str | None = None,
        until: str | None = None,
    ) -> set[str]:
        """Return stored candle open times (projection-only) for gap detection."""
        handle = await get_db()
        query: dict[str, Any] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": source,
        }
        time_filter: dict[str, Any] = {}
        if since is not None:
            time_filter["$gte"] = since
        if until is not None:
            time_filter["$lte"] = until
        if time_filter:
            query["time"] = time_filter

        cursor = handle.db[self.COLLECTION].find(query, {"_id": 0, "time": 1})
        docs = await cursor.to_list(length=None)
        return {str(doc["time"]) for doc in docs if doc.get("time")}

    async def count_candles(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> int:
        handle = await get_db()
        return await handle.db[self.COLLECTION].count_documents(
            {"symbol": symbol, "timeframe": timeframe, "source": source},
        )
