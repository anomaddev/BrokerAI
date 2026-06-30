from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.client import get_db
from brokerai.trading.analysis_runs import analysis_result_to_document, serialize_analysis_run
from brokerai.trading.types import AnalysisResult


class StrategyAnalysisRunsRepository:
    COLLECTION = "strategy_analysis_runs"

    async def insert_from_result(
        self,
        result: AnalysisResult,
        *,
        candle_time: datetime | str | None,
    ) -> dict[str, Any]:
        doc = analysis_result_to_document(result, candle_time=candle_time)
        handle = await get_db()
        await handle.db[self.COLLECTION].insert_one(doc)
        return serialize_analysis_run(doc)

    async def list_recent(
        self,
        *,
        strategy_id: str | None = None,
        pair: str | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        handle = await get_db()
        query: dict[str, Any] = {}
        if strategy_id:
            query["strategy_id"] = strategy_id
        if pair:
            query["pair"] = pair
        if before is not None:
            when = (
                before.astimezone(timezone.utc)
                if before.tzinfo
                else before.replace(tzinfo=timezone.utc)
            )
            query["analyzed_at"] = {"$lt": when}

        cursor = (
            handle.db[self.COLLECTION]
            .find(query, {"_id": 0})
            .sort("analyzed_at", -1)
            .limit(max(1, min(limit, 200)))
        )
        rows = await cursor.to_list(length=limit)
        return [serialize_analysis_run(row) for row in rows]

    async def get_by_id(self, run_id: str) -> dict[str, Any] | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one({"id": run_id}, {"_id": 0})
        if doc is None:
            return None
        return serialize_analysis_run(doc)

    async def update_execution(self, run_id: str, execution: dict[str, Any]) -> bool:
        handle = await get_db()
        result = await handle.db[self.COLLECTION].update_one(
            {"id": run_id},
            {"$set": {"execution": execution}},
        )
        return result.matched_count > 0
