from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from brokerai.db.market_data_timeseries import (
    COLLECTION,
    TIME_FIELD,
    candle_open_time_from_document,
    candle_open_time_to_datetime,
    candle_to_timeseries_document,
    timeseries_document_to_candle,
)
from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import MarketCandle


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


def _row_to_document(row: MarketCandle) -> dict[str, Any]:
    return {
        TIME_FIELD: row.ts,
        "symbol": row.symbol,
        "timeframe": row.timeframe,
        "source": row.source,
        "time": row.time,
        "open": row.open,
        "high": row.high,
        "low": row.low,
        "close": row.close,
        "volume": row.volume,
        "sessions": row.sessions,
        "trading_day_et": row.trading_day_et,
        "fetched_at": row.fetched_at,
        "expires_at": row.expires_at,
    }


def _document_to_row_values(
    symbol: str,
    timeframe: str,
    source: str,
    document: dict[str, Any],
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "source": source,
        "ts": document[TIME_FIELD],
        "time": document["time"],
        "open": document["open"],
        "high": document["high"],
        "low": document["low"],
        "close": document["close"],
        "volume": document.get("volume", 0),
        "sessions": document.get("sessions"),
        "trading_day_et": document.get("trading_day_et"),
        "fetched_at": document["fetched_at"],
        "expires_at": document.get("expires_at"),
    }


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
        """Insert OHLCV candles into the cache (idempotent per open time)."""
        if not candles:
            return 0

        now = datetime.now(timezone.utc)
        row_values: list[dict[str, Any]] = []

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
                row_values.append(_document_to_row_values(symbol, timeframe, source, document))

        if not row_values:
            return 0

        async with session_scope() as session:
            bind = session.get_bind()
            dialect = bind.dialect.name if bind is not None else "postgresql"

            if dialect == "postgresql":
                stmt = pg_insert(MarketCandle).values(row_values)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_market_candles_series_ts",
                    set_={
                        "time": stmt.excluded.time,
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume,
                        "sessions": stmt.excluded.sessions,
                        "trading_day_et": stmt.excluded.trading_day_et,
                        "fetched_at": stmt.excluded.fetched_at,
                        "expires_at": stmt.excluded.expires_at,
                    },
                )
                await session.execute(stmt)
            else:
                timestamps = [values["ts"] for values in row_values]
                await session.execute(
                    delete(MarketCandle).where(
                        MarketCandle.symbol == symbol,
                        MarketCandle.timeframe == timeframe,
                        MarketCandle.source == source,
                        MarketCandle.ts.in_(timestamps),
                    )
                )
                await session.execute(insert(MarketCandle), row_values)

        return len(row_values)

    async def latest_candle_time(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> str | None:
        async with session_scope() as session:
            stmt = (
                select(MarketCandle.time, MarketCandle.ts)
                .where(
                    MarketCandle.symbol == symbol,
                    MarketCandle.timeframe == timeframe,
                    MarketCandle.source == source,
                )
                .order_by(MarketCandle.ts.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).first()
            if not row:
                return None
            return candle_open_time_from_document({"time": row[0], TIME_FIELD: row[1]})

    async def earliest_candle_time(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> str | None:
        async with session_scope() as session:
            stmt = (
                select(MarketCandle.time, MarketCandle.ts)
                .where(
                    MarketCandle.symbol == symbol,
                    MarketCandle.timeframe == timeframe,
                    MarketCandle.source == source,
                )
                .order_by(MarketCandle.ts.asc())
                .limit(1)
            )
            row = (await session.execute(stmt)).first()
            if not row:
                return None
            return candle_open_time_from_document({"time": row[0], TIME_FIELD: row[1]})

    def _series_query(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        *,
        since: str | None = None,
        until: str | None = None,
        sessions: list[str] | None = None,
    ):
        stmt = select(MarketCandle).where(
            MarketCandle.symbol == symbol,
            MarketCandle.timeframe == timeframe,
            MarketCandle.source == source,
        )
        if since is not None:
            since_dt = candle_open_time_to_datetime(since)
            if since_dt is not None:
                stmt = stmt.where(MarketCandle.ts >= since_dt)
        if until is not None:
            until_dt = candle_open_time_to_datetime(until)
            if until_dt is not None:
                stmt = stmt.where(MarketCandle.ts <= until_dt)
        if sessions:
            stmt = stmt.where(MarketCandle.sessions.is_not(None))
        return stmt

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
        async with session_scope() as session:
            stmt = self._series_query(
                symbol,
                timeframe,
                source,
                since=since,
                until=until,
                sessions=sessions,
            ).order_by(MarketCandle.ts.asc() if ascending else MarketCandle.ts.desc())
            if limit is not None:
                stmt = stmt.limit(max(1, limit))

            rows = (await session.execute(stmt)).scalars().all()
            documents = [_row_to_document(row) for row in rows]
            if sessions:
                session_set = set(sessions)
                documents = [
                    doc
                    for doc in documents
                    if isinstance(doc.get("sessions"), list)
                    and session_set.intersection(doc["sessions"])
                ]
            documents = _dedupe_candle_rows(documents)
            return [timeseries_document_to_candle(row) for row in documents]

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
        after_dt = candle_open_time_to_datetime(after)
        if after_dt is None:
            return []

        async with session_scope() as session:
            stmt = (
                select(MarketCandle)
                .where(
                    MarketCandle.symbol == symbol,
                    MarketCandle.timeframe == timeframe,
                    MarketCandle.source == source,
                    MarketCandle.ts > after_dt,
                )
                .order_by(MarketCandle.ts.asc())
                .limit(max(1, limit))
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [timeseries_document_to_candle(_row_to_document(row)) for row in rows]

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
        async with session_scope() as session:
            stmt = self._series_query(symbol, timeframe, source, since=since, until=until)
            rows = (await session.execute(stmt)).scalars().all()
            times: set[str] = set()
            for row in rows:
                time_value = candle_open_time_from_document(_row_to_document(row))
                if time_value:
                    times.add(time_value)
            return times

    async def count_candles(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> int:
        async with session_scope() as session:
            stmt = select(func.count()).select_from(MarketCandle).where(
                MarketCandle.symbol == symbol,
                MarketCandle.timeframe == timeframe,
                MarketCandle.source == source,
            )
            return int((await session.execute(stmt)).scalar_one())
