from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.db.repositories.strategy_analysis_runs import StrategyAnalysisRunsRepository
from brokerai.trading.analysis_runs import analysis_result_to_document, serialize_analysis_run
from brokerai.trading.types import AnalysisResult


def _sample_result(*, run_id: str | None = None) -> AnalysisResult:
    return AnalysisResult(
        strategy_id="strategy-1",
        strategy_name="Test EMA",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.72,
        direction="long",
        min_candles=63,
        signal_type="ema_crossover",
        metadata={
            "signal": "bullish_cross",
            "filters": {"adx": {"passed": True, "adx": 28.0, "threshold": 25}},
            "filters_passed": True,
        },
        analyzed_at=datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc),
        run_id=run_id,
    )


def test_analysis_result_to_document_includes_live_run_type():
    doc = analysis_result_to_document(
        _sample_result(),
        candle_time="2026-01-01T00:15:00.000000000Z",
    )
    assert doc["run_type"] == "live"
    assert doc["strategy_id"] == "strategy-1"
    assert doc["execution"] is None


@pytest.mark.asyncio
async def test_strategy_analysis_runs_repository_insert_list_get_update():
    stored: dict[str, dict] = {}

    async def insert_one(doc):
        stored[doc["id"]] = doc

    async def update_one(filter_doc, update_doc):
        run_id = filter_doc["id"]
        if run_id not in stored:
            return MagicMock(matched_count=0)
        stored[run_id] = {**stored[run_id], **update_doc["$set"]}
        return MagicMock(matched_count=1)

    async def delete_one(query):
        run_id = query["id"]
        if run_id in stored:
            del stored[run_id]
            return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    cursor = MagicMock()

    async def to_list(length=200):
        rows = list(stored.values())
        rows.sort(key=lambda row: row["analyzed_at"], reverse=True)
        return rows[:length]

    cursor.to_list = AsyncMock(side_effect=to_list)
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    collection = MagicMock()
    collection.insert_one = AsyncMock(side_effect=insert_one)
    collection.update_one = AsyncMock(side_effect=update_one)
    collection.delete_one = AsyncMock(side_effect=delete_one)
    collection.find_one = AsyncMock(
        side_effect=lambda query, projection: stored.get(query["id"])
    )
    collection.find.return_value = cursor
    db = MagicMock()
    db.__getitem__.return_value = collection
    handle = MagicMock()
    handle.db = db

    repo = StrategyAnalysisRunsRepository()
    result = _sample_result()

    with patch(
        "brokerai.db.repositories.strategy_analysis_runs.get_db",
        AsyncMock(return_value=handle),
    ):
        inserted = await repo.insert_from_result(
            result,
            candle_time="2026-01-01T00:15:00.000000000Z",
        )
        assert inserted["id"]
        assert inserted["pair"] == "EUR/USD"
        assert inserted["confidence"] == 0.72

        listed = await repo.list_recent(strategy_id="strategy-1", limit=10)
        assert len(listed) == 1
        assert listed[0]["strategy_name"] == "Test EMA"

        fetched = await repo.get_by_id(inserted["id"])
        assert fetched is not None
        assert fetched["signal_type"] == "ema_crossover"

        updated = await repo.update_execution(
            inserted["id"],
            {
                "processed_at": "2026-01-01T00:16:00+00:00",
                "gates_passed": False,
                "gate_reasons": ["no_signal"],
                "priority_winner": False,
                "intent_queued": False,
                "intent": None,
            },
        )
        assert updated is True

        after_update = await repo.get_by_id(inserted["id"])
        assert after_update is not None
        assert after_update["execution"]["gates_passed"] is False

        deleted = await repo.delete_by_id(inserted["id"])
        assert deleted is True
        assert await repo.get_by_id(inserted["id"]) is None


def test_serialize_analysis_run_formats_datetimes():
    doc = analysis_result_to_document(
        _sample_result(),
        candle_time=datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc),
    )
    serialized = serialize_analysis_run(doc)
    assert serialized["analyzed_at"].endswith("+00:00")
    assert serialized["candle_time"].endswith("+00:00")
