from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from brokerai.db.repositories.backtest_runs import (
    BACKTEST_RUN_STATUS_COMPLETED,
    BACKTEST_RUN_STATUS_QUEUED,
    BacktestRunsRepository,
    build_queued_run_document,
    normalize_backtest_run_status,
    serialize_backtest_run,
)


pytestmark = pytest.mark.usefixtures("sqlite_db")


def _sample_strategy(**overrides: object) -> dict:
    base = {
        "id": "strategy-1",
        "name": "EMA Cross",
        "asset_class": "forex",
        "timeframe": "M15",
        "instruments": ["EUR/USD", "GBP/USD"],
        "params": {"timeframe": "M15", "fast_ema": 9},
    }
    base.update(overrides)
    return base


def test_normalize_backtest_run_status_defaults_to_queued():
    assert normalize_backtest_run_status(None) == BACKTEST_RUN_STATUS_QUEUED
    assert normalize_backtest_run_status("") == BACKTEST_RUN_STATUS_QUEUED
    assert normalize_backtest_run_status("not_run") == BACKTEST_RUN_STATUS_QUEUED
    assert normalize_backtest_run_status("completed") == BACKTEST_RUN_STATUS_COMPLETED


def test_build_queued_run_document_snapshots_strategy():
    doc = build_queued_run_document(_sample_strategy())
    assert doc["strategy_id"] == "strategy-1"
    assert doc["strategy_name"] == "EMA Cross"
    assert doc["status"] == BACKTEST_RUN_STATUS_QUEUED
    assert doc["timeframe"] == "M15"
    assert doc["instruments"] == ["EUR/USD", "GBP/USD"]
    assert doc["stats"]["total_trades"] is None
    assert doc["params_snapshot"]["fast_ema"] == 9
    assert doc["started_at"] is None
    assert doc["finished_at"] is None


def test_serialize_backtest_run_includes_asset_class_label():
    doc = build_queued_run_document(_sample_strategy())
    payload = serialize_backtest_run(doc)
    assert payload["asset_class_label"] == "Forex"
    assert payload["status"] == BACKTEST_RUN_STATUS_QUEUED


@pytest.mark.asyncio
async def test_create_list_get_delete_backtest_runs():
    repo = BacktestRunsRepository()
    created = await repo.create_queued_runs(
        [
            _sample_strategy(),
            _sample_strategy(id="strategy-2", name="Custom", asset_class="crypto", timeframe="H1"),
        ]
    )
    assert len(created) == 2
    assert all(run["status"] == BACKTEST_RUN_STATUS_QUEUED for run in created)

    listed = await repo.list_runs(limit=10)
    assert len(listed) == 2

    by_strategy = await repo.list_runs(strategy_id="strategy-1", limit=10)
    assert len(by_strategy) == 1
    assert by_strategy[0]["strategy_name"] == "EMA Cross"

    by_status = await repo.list_runs(status=BACKTEST_RUN_STATUS_QUEUED, limit=10)
    assert len(by_status) == 2

    fetched = await repo.get_by_id(created[0]["id"])
    assert fetched is not None
    assert fetched["strategy_id"] == "strategy-1"

    deleted = await repo.delete_by_id(created[0]["id"])
    assert deleted is True
    assert await repo.get_by_id(created[0]["id"]) is None
    assert len(await repo.list_runs(limit=10)) == 1


@pytest.mark.asyncio
async def test_list_runs_respects_before_cursor():
    repo = BacktestRunsRepository()
    created = (await repo.create_queued_runs([_sample_strategy()]))[0]
    created_at = datetime.fromisoformat(str(created["created_at"]).replace("Z", "+00:00"))

    include = await repo.list_runs(before=created_at + timedelta(seconds=1), limit=10)
    assert any(run["id"] == created["id"] for run in include)

    exclude = await repo.list_runs(before=created_at, limit=10)
    assert all(run["id"] != created["id"] for run in exclude)
