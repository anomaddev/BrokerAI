from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from brokerai.db.client import get_db
from brokerai.trading.analysis_runs import (
    analysis_result_to_document,
    normalize_candle_time,
    serialize_analysis_run,
)
from brokerai.trading.types import AnalysisResult


class StrategyAnalysisRunsRepository:
    COLLECTION = "strategy_analysis_runs"

    @staticmethod
    def _dedupe_filter(
        *,
        strategy_id: str,
        pair: str,
        candle_time: datetime,
        analysis_purpose: str = "entry",
        trade_id: str | None = None,
    ) -> dict[str, Any]:
        purpose = analysis_purpose if analysis_purpose in {"entry", "exit"} else "entry"
        filt: dict[str, Any] = {
            "strategy_id": strategy_id,
            "pair": pair,
            "candle_time": candle_time,
            "analysis_purpose": purpose,
        }
        if purpose == "exit" and trade_id:
            filt["trade_id"] = trade_id
        return filt

    @staticmethod
    def _merge_fields(existing: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
        update_fields: dict[str, Any] = {}
        purpose = str(doc.get("analysis_purpose") or "entry")
        if existing.get("run_type") != "manual":
            update_fields.update(
                {
                    "strategy_name": doc["strategy_name"],
                    "timeframe": doc["timeframe"],
                    "direction": doc["direction"],
                    "confidence": doc["confidence"],
                    "signal_type": doc["signal_type"],
                    "min_candles": doc["min_candles"],
                    "metadata": doc["metadata"],
                    "analyzed_at": doc["analyzed_at"],
                }
            )
        if purpose == "exit" and doc.get("execution") is not None:
            update_fields["execution"] = doc["execution"]
        if doc.get("run_type") == "manual" or existing.get("run_type") == "manual":
            update_fields["run_type"] = "manual"
        return update_fields

    async def find_by_strategy_pair_candle(
        self,
        *,
        strategy_id: str,
        pair: str,
        candle_time: datetime | str,
    ) -> dict[str, Any] | None:
        """Return an existing run for the same strategy, pair, and analyzed candle."""
        when = normalize_candle_time(candle_time)
        if when is None:
            return None
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one(
            self._dedupe_filter(strategy_id=strategy_id, pair=pair, candle_time=when),
            {"_id": 0},
        )
        if doc is None:
            return None
        return serialize_analysis_run(doc)

    async def _merge_existing(
        self,
        collection,
        existing: dict[str, Any],
        doc: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = existing["id"]
        update_fields = self._merge_fields(existing, doc)
        if update_fields:
            await collection.update_one({"id": run_id}, {"$set": update_fields})
            return {**existing, **update_fields}
        return existing

    async def _upsert_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        handle = await get_db()
        collection = handle.db[self.COLLECTION]

        candle_dt = doc.get("candle_time")
        strategy_id = str(doc.get("strategy_id") or "")
        pair = str(doc.get("pair") or "")
        purpose = str(doc.get("analysis_purpose") or "entry")
        trade_id = str(doc.get("trade_id") or "") or None
        if candle_dt is not None and strategy_id and pair:
            filter_doc = self._dedupe_filter(
                strategy_id=strategy_id,
                pair=pair,
                candle_time=candle_dt,
                analysis_purpose=purpose,
                trade_id=trade_id,
            )
            existing = await collection.find_one(filter_doc)
            if existing is not None:
                merged = await self._merge_existing(collection, existing, doc)
                return serialize_analysis_run(merged)

            try:
                await collection.insert_one(doc)
            except DuplicateKeyError:
                existing = await collection.find_one(filter_doc)
                if existing is None:
                    raise
                merged = await self._merge_existing(collection, existing, doc)
                return serialize_analysis_run(merged)
            return serialize_analysis_run(doc)

        await collection.insert_one(doc)
        return serialize_analysis_run(doc)

    async def insert_from_result(
        self,
        result: AnalysisResult,
        *,
        candle_time: datetime | str | None,
    ) -> dict[str, Any]:
        doc = analysis_result_to_document(result, candle_time=candle_time)
        return await self._upsert_document(doc)

    async def insert_from_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Insert or merge a pre-built analysis run document (e.g. exit analysis)."""
        return await self._upsert_document(doc)

    async def list_recent(
        self,
        *,
        strategy_id: str | None = None,
        pair: str | None = None,
        analysis_purpose: str | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        handle = await get_db()
        query: dict[str, Any] = {}
        if strategy_id:
            query["strategy_id"] = strategy_id
        if pair:
            query["pair"] = pair
        if analysis_purpose in {"entry", "exit"}:
            query["analysis_purpose"] = analysis_purpose
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

    async def delete_by_id(self, run_id: str) -> bool:
        """Remove a persisted analysis run by id."""
        handle = await get_db()
        result = await handle.db[self.COLLECTION].delete_one({"id": run_id})
        return result.deleted_count > 0

    async def set_run_type(self, run_id: str, run_type: str) -> bool:
        """Update the persisted run type (e.g. ``live`` → ``manual``)."""
        handle = await get_db()
        result = await handle.db[self.COLLECTION].update_one(
            {"id": run_id},
            {"$set": {"run_type": run_type}},
        )
        return result.matched_count > 0
