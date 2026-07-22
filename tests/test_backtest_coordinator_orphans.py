"""Orphan reclaim for startup backtests marked running outside the API process."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokerai.ai_strategy.startup import _start_backtest_if_needed
from brokerai.backtesting.coordinator import BacktestCoordinator
from brokerai.db.repositories.backtest_runs import (
    BACKTEST_RUN_STATUS_CANCELLED,
    BACKTEST_RUN_STATUS_QUEUED,
    BACKTEST_RUN_STATUS_RUNNING,
    BacktestRunsRepository,
)

pytestmark = pytest.mark.usefixtures("sqlite_db")


def _sample_strategy() -> dict:
    return {
        "id": "strategy-orphan",
        "name": "Orphan BT",
        "asset_class": "forex",
        "timeframe": "M15",
        "instruments": ["EUR/USD"],
        "params": {"timeframe": "M15"},
    }


@pytest.mark.asyncio
async def test_finish_orphaned_cancel_requests():
    repo = BacktestRunsRepository()
    created = await repo.create_queued_runs([_sample_strategy()], instrument="EUR/USD")
    run_id = created[0]["id"]
    await repo.mark_running(run_id)
    await repo.request_cancel(run_id)

    finished = await repo.finish_orphaned_cancel_requests()
    assert run_id in finished
    doc = await repo.get_by_id(run_id)
    assert doc is not None
    assert doc["status"] == BACKTEST_RUN_STATUS_CANCELLED
    assert "before worker" in str(doc.get("status_message") or "").lower()


@pytest.mark.asyncio
async def test_start_backtest_leaves_queued_when_coordinator_not_started():
    repo = BacktestRunsRepository()
    created = await repo.create_queued_runs([_sample_strategy()], instrument="EUR/USD")
    run_id = created[0]["id"]

    coord = BacktestCoordinator(use_processes=False)
    assert coord.is_started is False

    with patch(
        "brokerai.backtesting.coordinator.get_backtest_coordinator",
        return_value=coord,
    ):
        await _start_backtest_if_needed(run_id)

    doc = await repo.get_by_id(run_id)
    assert doc is not None
    assert doc["status"] == BACKTEST_RUN_STATUS_QUEUED


@pytest.mark.asyncio
async def test_start_backtest_marks_running_when_coordinator_started():
    repo = BacktestRunsRepository()
    created = await repo.create_queued_runs([_sample_strategy()], instrument="EUR/USD")
    run_id = created[0]["id"]

    coord = BacktestCoordinator(use_processes=False)
    coord._task = MagicMock()
    coord._task.done.return_value = False
    assert coord.is_started is True

    with patch(
        "brokerai.backtesting.coordinator.get_backtest_coordinator",
        return_value=coord,
    ):
        await _start_backtest_if_needed(run_id)

    doc = await repo.get_by_id(run_id)
    assert doc is not None
    assert doc["status"] == BACKTEST_RUN_STATUS_RUNNING
    assert run_id in coord._manual_ready


@pytest.mark.asyncio
async def test_reclaim_orphaned_runs_adds_manual_ready():
    repo = BacktestRunsRepository()
    created = await repo.create_queued_runs([_sample_strategy()], instrument="EUR/USD")
    run_id = created[0]["id"]
    await repo.mark_running(run_id)

    coord = BacktestCoordinator(use_processes=False)
    await coord._reclaim_orphaned_runs(repo)
    assert run_id in coord._manual_ready
