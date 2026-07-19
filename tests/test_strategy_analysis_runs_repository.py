from __future__ import annotations

from datetime import datetime, timezone

import pytest

from brokerai.db.repositories.strategy_analysis_runs import StrategyAnalysisRunsRepository
from brokerai.trading.analysis_runs import analysis_result_to_document, normalize_candle_time, serialize_analysis_run
from brokerai.trading.types import AnalysisResult


pytestmark = pytest.mark.usefixtures("sqlite_db")


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
    assert doc["candle_time"] == datetime(2026, 1, 1, 0, 15)


def test_normalize_candle_time_strips_timezone_and_subseconds():
    assert normalize_candle_time("2026-01-01T00:15:00.000000000Z") == datetime(2026, 1, 1, 0, 15)
    assert normalize_candle_time(
        datetime(2026, 1, 1, 0, 15, 30, 123456, tzinfo=timezone.utc)
    ) == datetime(2026, 1, 1, 0, 15, 30)


@pytest.mark.asyncio
async def test_strategy_analysis_runs_repository_insert_list_get_update():
    repo = StrategyAnalysisRunsRepository()
    result = _sample_result()

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


@pytest.mark.asyncio
async def test_insert_from_result_dedupes_by_strategy_pair_candle():
    repo = StrategyAnalysisRunsRepository()
    candle_time = datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc)

    first = await repo.insert_from_result(
        _sample_result(),
        candle_time=candle_time,
    )
    second_result = _sample_result()
    second_result.metadata = {**second_result.metadata, "signal": "bearish_cross"}
    second = await repo.insert_from_result(
        second_result,
        candle_time=candle_time,
    )

    assert second["id"] == first["id"]
    listed = await repo.list_recent(strategy_id="strategy-1", limit=10)
    assert len(listed) == 1
    assert listed[0]["metadata"]["signal"] == "bearish_cross"


@pytest.mark.asyncio
async def test_insert_from_result_preserves_manual_analysis_fields():
    repo = StrategyAnalysisRunsRepository()
    candle_time = datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc)

    manual = await repo.insert_from_result(
        _sample_result(),
        candle_time=candle_time,
    )
    await repo.set_run_type(manual["id"], "manual")

    live_result = _sample_result()
    live_result.metadata = {**live_result.metadata, "signal": "bearish_cross"}
    merged = await repo.insert_from_result(
        live_result,
        candle_time=candle_time,
    )

    assert merged["id"] == manual["id"]
    assert merged["run_type"] == "manual"
    assert merged["metadata"]["signal"] == "bullish_cross"


@pytest.mark.asyncio
async def test_insert_from_result_retries_after_duplicate_key_error():
    repo = StrategyAnalysisRunsRepository()
    candle_time = datetime(2026, 1, 1, 0, 15)

    existing_doc = analysis_result_to_document(_sample_result(), candle_time=candle_time)
    existing_doc["run_type"] = "manual"
    await repo.insert_from_document(existing_doc)

    merged = await repo.insert_from_result(
        _sample_result(),
        candle_time=candle_time,
    )

    assert merged["id"] == existing_doc["id"]
    listed = await repo.list_recent(strategy_id="strategy-1", limit=10)
    assert len(listed) == 1
    assert listed[0]["run_type"] == "manual"


def test_serialize_analysis_run_formats_datetimes():
    doc = analysis_result_to_document(
        _sample_result(),
        candle_time=datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc),
    )
    serialized = serialize_analysis_run(doc)
    assert serialized["analyzed_at"].endswith("+00:00")
    assert serialized["candle_time"].endswith("+00:00")
