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


@pytest.mark.asyncio
async def test_claim_for_worker_is_exclusive():
    repo = BacktestRunsRepository()
    created = await repo.create_queued_runs([_sample_strategy()], instrument="EUR/USD")
    run_id = created[0]["id"]
    await repo.mark_running(run_id)

    first = await repo.claim_for_worker(run_id, "token-a")
    assert first is not None
    assert await repo.worker_owns(run_id, "token-a")
    assert await repo.claim_for_worker(run_id, "token-b") is None
    assert not await repo.worker_owns(run_id, "token-b")

    assert await repo.touch_worker_heartbeat(run_id, "token-a")
    assert not await repo.touch_worker_heartbeat(run_id, "token-b")

    ok = await repo.update_progress(run_id, progress_pct=10, worker_token="token-a")
    assert ok is True
    assert await repo.update_progress(run_id, progress_pct=20, worker_token="token-b") is False


@pytest.mark.asyncio
async def test_list_claimable_skips_fresh_worker_lease():
    repo = BacktestRunsRepository()
    created = await repo.create_queued_runs([_sample_strategy()], instrument="EUR/USD")
    run_id = created[0]["id"]
    await repo.mark_running(run_id)

    assert run_id in await repo.list_claimable_manual_starts()
    await repo.claim_for_worker(run_id, "token-a")
    assert run_id not in await repo.list_claimable_manual_starts()

    await repo.clear_worker_claim(run_id, "token-a")
    assert run_id in await repo.list_claimable_manual_starts()


@pytest.mark.asyncio
async def test_reclaim_skips_freshly_claimed_runs():
    repo = BacktestRunsRepository()
    created = await repo.create_queued_runs([_sample_strategy()], instrument="EUR/USD")
    run_id = created[0]["id"]
    await repo.mark_running(run_id)
    await repo.claim_for_worker(run_id, "token-a")

    coord = BacktestCoordinator(use_processes=False)
    await coord._reclaim_orphaned_runs(repo)
    assert run_id not in coord._manual_ready


@pytest.mark.asyncio
async def test_insert_many_ignores_duplicate_sequences():
    from brokerai.db.repositories.backtest_actions import BacktestActionsRepository

    repo = BacktestRunsRepository()
    created = await repo.create_queued_runs([_sample_strategy()], instrument="EUR/USD")
    run_id = created[0]["id"]
    actions_repo = BacktestActionsRepository()

    batch = [
        {"sequence": 0, "kind": "signal", "message": "first"},
        {"sequence": 1, "kind": "entry", "message": "enter"},
    ]
    assert await actions_repo.insert_many(run_id, batch) == 2
    # Second overlapping worker should not create duplicate sequences.
    assert await actions_repo.insert_many(run_id, batch) == 0
    rows = await actions_repo.list_for_run(run_id, limit=100)
    assert [r["sequence"] for r in rows] == [0, 1]
    assert [r["message"] for r in rows] == ["first", "enter"]
