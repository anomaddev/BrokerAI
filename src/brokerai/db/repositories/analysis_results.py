from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import AnalysisResultRow


class AnalysisResultsRepository:
    COLLECTION = "analysis_results"

    async def insert(
        self,
        symbol: str,
        analysis_type: str,
        payload: dict[str, Any],
        *,
        score: float | None = None,
    ) -> None:
        created_at = datetime.now(timezone.utc)
        doc = {
            "symbol": symbol,
            "analysis_type": analysis_type,
            "score": score,
            "payload": payload,
            "created_at": created_at,
        }
        async with session_scope() as session:
            session.add(
                AnalysisResultRow(symbol=symbol, created_at=created_at, doc=doc)
            )

    async def find_recent(self, symbol: str, limit: int = 10) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = (
                select(AnalysisResultRow)
                .where(AnalysisResultRow.symbol == symbol)
                .order_by(AnalysisResultRow.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [dict(row.doc) for row in rows]
