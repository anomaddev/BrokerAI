from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from brokerai.web.app import app
from brokerai.web.routes.auth import require_auth


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[require_auth] = lambda: "test-user"
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_list_backtest_runs_requires_auth() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        response = test_client.get("/api/backtest-runs")
    assert response.status_code == 401


@patch("brokerai.web.routes.backtest_runs.BacktestRunsRepository")
def test_list_backtest_runs_returns_payload(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.list_runs.return_value = [
        {
            "id": "run-1",
            "strategy_id": "strategy-1",
            "strategy_name": "EMA Cross",
            "asset_class": "forex",
            "asset_class_label": "Forex",
            "timeframe": "M15",
            "instruments": ["EUR/USD"],
            "status": "queued",
            "created_at": "2026-01-01T00:00:00+00:00",
            "started_at": None,
            "finished_at": None,
            "error": None,
            "stats": {
                "total_trades": None,
                "win_rate": None,
                "realized_pnl": None,
                "max_drawdown": None,
            },
            "params_snapshot": None,
        }
    ]

    response = client.get(
        "/api/backtest-runs?strategy_id=strategy-1&status=queued&limit=25"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["latest"]["id"] == "run-1"
    assert len(body["runs"]) == 1
    repo.list_runs.assert_awaited_once_with(
        strategy_id="strategy-1",
        status="queued",
        limit=25,
        before=None,
    )


@patch("brokerai.web.routes.backtest_runs.BacktestRunsRepository")
def test_get_backtest_run_returns_detail(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = {
        "id": "run-1",
        "strategy_id": "strategy-1",
        "strategy_name": "EMA Cross",
        "asset_class": "forex",
        "asset_class_label": "Forex",
        "timeframe": "M15",
        "instruments": ["EUR/USD"],
        "status": "queued",
        "created_at": "2026-01-01T00:00:00+00:00",
        "started_at": None,
        "finished_at": None,
        "error": None,
        "stats": {
            "total_trades": None,
            "win_rate": None,
            "realized_pnl": None,
            "max_drawdown": None,
        },
        "params_snapshot": None,
    }

    response = client.get("/api/backtest-runs/run-1")

    assert response.status_code == 200
    assert response.json()["strategy_name"] == "EMA Cross"


@patch("brokerai.web.routes.backtest_runs.BacktestRunsRepository")
def test_get_backtest_run_not_found(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = None

    response = client.get("/api/backtest-runs/missing")

    assert response.status_code == 404


@patch("brokerai.web.routes.backtest_runs.BacktestRunsRepository")
def test_delete_backtest_run(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.delete_by_id.return_value = True

    response = client.delete("/api/backtest-runs/run-1")

    assert response.status_code == 200
    assert response.json() == {"id": "run-1", "status": "deleted"}
    repo.delete_by_id.assert_awaited_once_with("run-1")


@patch("brokerai.web.routes.strategies.BacktestRunsRepository")
@patch("brokerai.web.routes.strategies.StrategiesRepository")
def test_queue_strategy_backtests_creates_runs(
    mock_strategies_cls,
    mock_runs_cls,
    client: TestClient,
) -> None:
    strategies_repo = AsyncMock()
    mock_strategies_cls.return_value = strategies_repo
    strategies_repo.queue_backtests.return_value = [
        {
            "id": "strategy-1",
            "name": "EMA Cross",
            "asset_class": "forex",
            "asset_class_label": "Forex",
            "timeframe": "M15",
            "description": "",
            "enabled": False,
            "backtest_status": "queued",
            "instruments": ["EUR/USD"],
            "stats": {},
            "created_at": None,
            "updated_at": None,
            "params": {"timeframe": "M15"},
        }
    ]

    runs_repo = AsyncMock()
    mock_runs_cls.return_value = runs_repo
    runs_repo.create_queued_runs.return_value = [
        {
            "id": "run-1",
            "strategy_id": "strategy-1",
            "strategy_name": "EMA Cross",
            "asset_class": "forex",
            "asset_class_label": "Forex",
            "timeframe": "M15",
            "instruments": ["EUR/USD"],
            "status": "queued",
            "created_at": "2026-01-01T00:00:00+00:00",
            "started_at": None,
            "finished_at": None,
            "error": None,
            "stats": {
                "total_trades": None,
                "win_rate": None,
                "realized_pnl": None,
                "max_drawdown": None,
            },
            "params_snapshot": {"timeframe": "M15"},
        }
    ]

    response = client.post("/api/strategies/backtest", json={"ids": ["strategy-1"]})

    assert response.status_code == 200
    body = response.json()
    assert body["queued"] == 1
    assert body["runs"][0]["id"] == "run-1"
    runs_repo.create_queued_runs.assert_awaited_once()
