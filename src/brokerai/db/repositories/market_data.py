from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.client import get_db
from brokerai.db.market_data_timeseries import (
    COLLECTION,
    TIME_FIELD,
    candle_open_time_from_document,
    candle_open_time_to_datetime,
    candle_to_timeseries_document,
    meta_query_filter,
    timeseries_document_to_candle,
)


def _dedupe_candle_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicate open times while preserving ascending ``ts`` order (last row wins)."""
    seen: set[int] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        ts = row.get(TIME_FIELD)
        if isinstance(ts, datetime):
            key = int(ts.astimezone(timezone.utc).timestamp())
        else:
            open_time = candle_open_time_from_document(row)
            parsed = candle_open_time_to_datetime(open_time) if open_time else None
            if parsed is None:
                continue
            key = int(parsed.timestamp())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


class MarketDataRepository:
    COLLECTION = COLLECTION

    async def upsert_candles(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        candles: list[dict[str, Any]],
        *,
        expires_at: datetime | None = None,
    ) -> int:
        """Insert OHLCV candles into the time-series cache (idempotent per open time).

        Time-series collections do not support in-place updates. Existing rows for
        the same ``(symbol, timeframe, source, ts)`` are deleted before insert.
        """
        if not candles:
            return 0

        handle = await get_db()
        now = datetime.now(timezone.utc)
        documents: list[dict[str, Any]] = []

        for candle in candles:
            document = candle_to_timeseries_document(
                symbol,
                timeframe,
                source,
                candle,
                fetched_at=now,
                expires_at=expires_at,
            )
            if document is not None:
                documents.append(document)

        if not documents:
            return 0

        collection = handle.db[self.COLLECTION]
        series_filter = meta_query_filter(symbol, timeframe, source)
        timestamps = [document[TIME_FIELD] for document in documents]
        await collection.delete_many({**series_filter, TIME_FIELD: {"$in": timestamps}})
        await collection.insert_many(documents, ordered=False)
        return len(documents)

    async def latest_candle_time(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> str | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            meta_query_filter(symbol, timeframe, source),
            {"_id": 0, "time": 1, TIME_FIELD: 1},
            sort=[(TIME_FIELD, -1)],
        )
        if not doc:
            return None
        return candle_open_time_from_document(doc)

    async def earliest_candle_time(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> str | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            meta_query_filter(symbol, timeframe, source),
            {"_id": 0, "time": 1, TIME_FIELD: 1},
            sort=[(TIME_FIELD, 1)],
        )
        if not doc:
            return None
        return candle_open_time_from_document(doc)

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
        query: dict[str, Any] = meta_query_filter(symbol, timeframe, source)
        time_filter: dict[str, Any] = {}
        if since is not None:
            since_dt = candle_open_time_to_datetime(since)
            if since_dt is not None:
                time_filter["$gte"] = since_dt
        if until is not None:
            until_dt = candle_open_time_to_datetime(until)
            if until_dt is not None:
                time_filter["$lte"] = until_dt
        if time_filter:
            query[TIME_FIELD] = time_filter
        if sessions:
            query["sessions"] = {"$in": sessions}

        cursor = handle.db[self.COLLECTION].find(query, {"_id": 0}).sort(
            TIME_FIELD,
            1 if ascending else -1,
        )
        if limit is not None:
            cursor = cursor.limit(max(1, limit))

        rows = await cursor.to_list(length=limit or 5000)
        rows = _dedupe_candle_rows(rows)
        return [timeseries_document_to_candle(row) for row in rows]

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
        after_dt = candle_open_time_to_datetime(after)
        if after_dt is None:
            return []

        cursor = (
            handle.db[self.COLLECTION]
            .find(
                {
                    **meta_query_filter(symbol, timeframe, source),
                    TIME_FIELD: {"$gt": after_dt},
                },
                {"_id": 0},
            )
            .sort(TIME_FIELD, 1)
            .limit(max(1, limit))
        )
        rows = await cursor.to_list(length=max(1, limit))
        return [timeseries_document_to_candle(row) for row in rows]

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
        query: dict[str, Any] = meta_query_filter(symbol, timeframe, source)
        time_filter: dict[str, Any] = {}
        if since is not None:
            since_dt = candle_open_time_to_datetime(since)
            if since_dt is not None:
                time_filter["$gte"] = since_dt
        if until is not None:
            until_dt = candle_open_time_to_datetime(until)
            if until_dt is not None:
                time_filter["$lte"] = until_dt
        if time_filter:
            query[TIME_FIELD] = time_filter

        cursor = handle.db[self.COLLECTION].find(query, {"_id": 0, "time": 1, TIME_FIELD: 1})
        docs = await cursor.to_list(length=None)
        times: set[str] = set()
        for doc in docs:
            time_value = candle_open_time_from_document(doc)
            if time_value:
                times.add(time_value)
        return times

    async def count_candles(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> int:
        handle = await get_db()
        return await handle.db[self.COLLECTION].count_documents(
            meta_query_filter(symbol, timeframe, source),
        )
