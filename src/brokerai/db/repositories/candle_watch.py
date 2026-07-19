from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import CandleWatchRow

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
        now = datetime.now(timezone.utc)
        doc = {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": source,
            "requester": requester,
            "bar_count": max(1, bar_count),
            "updated_at": now,
        }

        async with session_scope() as session:
            stmt = select(CandleWatchRow).where(
                CandleWatchRow.symbol == symbol,
                CandleWatchRow.timeframe == timeframe,
                CandleWatchRow.source == source,
                CandleWatchRow.requester == requester,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                session.add(
                    CandleWatchRow(
                        symbol=symbol,
                        timeframe=timeframe,
                        source=source,
                        requester=requester,
                        updated_at=now,
                        doc=doc,
                    )
                )
            else:
                row.updated_at = now
                row.doc = doc

    async def touch_watch(
        self,
        symbol: str,
        timeframe: str,
        source: str,
        requester: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with session_scope() as session:
            stmt = select(CandleWatchRow).where(
                CandleWatchRow.symbol == symbol,
                CandleWatchRow.timeframe == timeframe,
                CandleWatchRow.source == source,
                CandleWatchRow.requester == requester,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return
            doc = dict(row.doc)
            doc["updated_at"] = now
            row.updated_at = now
            row.doc = doc

    async def list_active_watches(
        self,
        *,
        source: str | None = None,
        max_age_seconds: int = DEFAULT_WATCH_MAX_AGE_SECONDS,
    ) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, max_age_seconds))
        async with session_scope() as session:
            stmt = select(CandleWatchRow).where(CandleWatchRow.updated_at >= cutoff)
            if source is not None:
                stmt = stmt.where(CandleWatchRow.source == source)
            stmt = stmt.limit(500)
            rows = (await session.execute(stmt)).scalars().all()
            return [dict(row.doc) for row in rows]
