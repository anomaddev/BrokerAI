from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.client import get_db


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
        handle = await get_db()
        await handle.db[self.COLLECTION].insert_one(
            {
                "symbol": symbol,
                "analysis_type": analysis_type,
                "score": score,
                "payload": payload,
                "created_at": datetime.now(timezone.utc),
            }
        )

    async def find_recent(self, symbol: str, limit: int = 10) -> list[dict[str, Any]]:
        handle = await get_db()
        cursor = (
            handle.db[self.COLLECTION]
            .find({"symbol": symbol}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)
