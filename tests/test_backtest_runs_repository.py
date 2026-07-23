from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from brokerai.db.repositories.backtest_runs import (
    BACKTEST_RUN_STATUS_COMPLETED,
    BACKTEST_RUN_STATUS_QUEUED,
    DEFAULT_ACCOUNT_MARGIN,
    MAX_ACCOUNT_MARGIN,
    MIN_ACCOUNT_MARGIN,
    BacktestRunsRepository,
    build_queued_run_document,
    normalize_account_margin,
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


def test_normalize_account_margin_defaults_and_bounds():
    assert normalize_account_margin(None) == DEFAULT_ACCOUNT_MARGIN
    assert normalize_account_margin("not-a-number") == DEFAULT_ACCOUNT_MARGIN
    assert normalize_account_margin(50) == MIN_ACCOUNT_MARGIN
    assert normalize_account_margin(99_999_999) == MAX_ACCOUNT_MARGIN
    assert normalize_account_margin(25_000) == 25_000.0


def test_build_queued_run_document_snapshots_strategy():
    doc = build_queued_run_document(_sample_strategy(), period="1y", instrument="EUR/USD")
    assert doc["strategy_id"] == "strategy-1"
    assert doc["strategy_name"] == "EMA Cross"
    assert doc["status"] == BACKTEST_RUN_STATUS_QUEUED
    assert doc["timeframe"] == "M15"
    assert doc["instruments"] == ["EUR/USD", "GBP/USD"]
    assert doc["instrument"] == "EUR/USD"
    assert doc["period"] == "1y"
    assert doc["account_margin"] == DEFAULT_ACCOUNT_MARGIN
    assert doc["stats"]["total_trades"] is None
    assert doc["params_snapshot"]["fast_ema"] == 9
    assert doc["started_at"] is None
    assert doc["finished_at"] is None
    assert doc["progress_pct"] == 0.0


def test_build_queued_run_document_persists_loop_mode():
    doc = build_queued_run_document(_sample_strategy(), loop_mode="explore")
    assert doc["loop_mode"] == "explore"
    payload = serialize_backtest_run(doc)
    assert payload["loop_mode"] == "explore"
    ignored = build_queued_run_document(_sample_strategy(), loop_mode="nope")
    assert ignored["loop_mode"] is None


def test_build_queued_run_document_persists_account_margin():
    doc = build_queued_run_document(_sample_strategy(), account_margin=50_000)
    assert doc["account_margin"] == 50_000.0
    payload = serialize_backtest_run(doc)
    assert payload["account_margin"] == 50_000.0


def test_serialize_backtest_run_includes_asset_class_label():
    doc = build_queued_run_document(_sample_strategy())
    payload = serialize_backtest_run(doc)
    assert payload["asset_class_label"] == "Forex"
    assert payload["status"] == BACKTEST_RUN_STATUS_QUEUED
    assert payload["account_margin"] == DEFAULT_ACCOUNT_MARGIN


@pytest.mark.asyncio
async def test_create_list_get_delete_backtest_runs():
    repo = BacktestRunsRepository()
    created = await repo.create_queued_runs(
        [
            _sample_strategy(),
            _sample_strategy(id="strategy-2", name="Custom", asset_class="crypto", timeframe="H1"),
        ],
        account_margin=12_500,
    )
    assert len(created) == 2
    assert all(run["status"] == BACKTEST_RUN_STATUS_QUEUED for run in created)
    assert all(run["account_margin"] == 12_500.0 for run in created)

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
