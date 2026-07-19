from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import CandleSyncStateRow


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

        async with session_scope() as session:
            stmt = select(CandleSyncStateRow).where(
                CandleSyncStateRow.symbol == symbol,
                CandleSyncStateRow.timeframe == timeframe,
                CandleSyncStateRow.source == source,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                session.add(
                    CandleSyncStateRow(
                        symbol=symbol,
                        timeframe=timeframe,
                        source=source,
                        doc=update,
                    )
                )
            else:
                doc = dict(row.doc)
                doc.update(update)
                row.doc = doc

    async def get_state(
        self,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> dict[str, Any] | None:
        async with session_scope() as session:
            stmt = select(CandleSyncStateRow).where(
                CandleSyncStateRow.symbol == symbol,
                CandleSyncStateRow.timeframe == timeframe,
                CandleSyncStateRow.source == source,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return dict(row.doc) if row else None

    async def list_states(self, *, source: str | None = None) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(CandleSyncStateRow)
            if source is not None:
                stmt = stmt.where(CandleSyncStateRow.source == source)
            rows = (await session.execute(stmt)).scalars().all()
            return [dict(row.doc) for row in rows]
