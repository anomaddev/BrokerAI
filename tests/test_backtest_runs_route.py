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


@patch("brokerai.web.routes.backtest_runs.BacktestActionsRepository")
@patch("brokerai.web.routes.backtest_runs.BacktestLogsRepository")
@patch("brokerai.web.routes.backtest_runs.BacktestRunsRepository")
def test_delete_backtest_run(
    mock_repo_cls,
    mock_logs_cls,
    mock_actions_cls,
    client: TestClient,
) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = {
        "id": "run-1",
        "status": "completed",
        "strategy_id": "strategy-1",
    }
    repo.delete_by_id.return_value = True
    mock_logs_cls.return_value.delete_for_run = AsyncMock(return_value=0)
    mock_actions_cls.return_value.delete_for_run = AsyncMock(return_value=0)

    response = client.delete("/api/backtest-runs/run-1")

    assert response.status_code == 200
    assert response.json() == {"id": "run-1", "status": "deleted"}
    repo.delete_by_id.assert_awaited_once_with("run-1")


def test_slice_candles_around_centers_window() -> None:
    from brokerai.web.routes.backtest_runs import slice_candles_around

    candles = [
        {"time": f"2024-01-01T{hour:02d}:00:00+00:00", "close": float(hour)}
        for hour in range(24)
    ]
    window = slice_candles_around(
        candles,
        around_iso="2024-01-01T12:00:00+00:00",
        limit=6,
    )
    assert len(window) == 6
    assert window[0]["time"].startswith("2024-01-01T09:")
    assert window[-1]["time"].startswith("2024-01-01T14:")


@patch("brokerai.web.routes.backtest_runs.CandleCache")
@patch("brokerai.web.routes.backtest_runs.BacktestRunsRepository")
def test_get_backtest_run_candles_reads_cache(
    mock_repo_cls,
    mock_cache_cls,
    client: TestClient,
) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = {
        "id": "run-1",
        "instrument": "USD/JPY",
        "instruments": ["USD/JPY"],
        "timeframe": "M15",
        "period": "6m",
        "period_start": "2026-01-18T00:00:00+00:00",
        "period_end": "2026-07-19T00:00:00+00:00",
        "status": "completed",
    }

    cache = AsyncMock()
    mock_cache_cls.return_value = cache
    cache.read_candles.return_value = [
        {
            "time": "2026-01-19T15:30:00.000000000Z",
            "open": 157.0,
            "high": 157.2,
            "low": 156.9,
            "close": 157.1,
            "volume": 10,
        }
    ]

    response = client.get("/api/backtest-runs/run-1/candles")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "USD/JPY"
    assert body["timeframe"] == "M15"
    assert len(body["candles"]) == 1
    cache.read_candles.assert_awaited()
    kwargs = cache.read_candles.await_args.kwargs
    assert kwargs["since"] == "2026-01-18T00:00:00+00:00"
    assert kwargs["until"] == "2026-07-19T00:00:00+00:00"


@patch("brokerai.web.routes.backtest_runs.CandleCache")
@patch("brokerai.web.routes.backtest_runs.BacktestRunsRepository")
def test_get_backtest_run_candles_around_centers_truncated_window(
    mock_repo_cls,
    mock_cache_cls,
    client: TestClient,
) -> None:
    from brokerai.web.routes import backtest_runs as routes

    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = {
        "id": "run-1",
        "instrument": "USD/JPY",
        "instruments": ["USD/JPY"],
        "timeframe": "M15",
        "period": "2y",
        "period_start": "2024-01-01T00:00:00+00:00",
        "period_end": "2026-01-01T00:00:00+00:00",
        "status": "completed",
    }

    original_limit = routes.BACKTEST_CANDLE_LIMIT_MAX
    routes.BACKTEST_CANDLE_LIMIT_MAX = 10
    try:
        cache = AsyncMock()
        mock_cache_cls.return_value = cache
        cache.read_candles.return_value = [
            {
                "time": f"2024-06-01T{hour:02d}:00:00.000000000Z",
                "open": 150.0,
                "high": 150.1,
                "low": 149.9,
                "close": 150.0,
                "volume": 1,
            }
            for hour in range(24)
        ]

        response = client.get(
            "/api/backtest-runs/run-1/candles",
            params={"around": "2024-06-01T12:00:00+00:00"},
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["candles"]) == 10
        assert body["around"] == "2024-06-01T12:00:00+00:00"
        times = [row["time"] for row in body["candles"]]
        assert any("T12:" in time or "T11:" in time for time in times)
        assert times[0] < times[-1]
    finally:
        routes.BACKTEST_CANDLE_LIMIT_MAX = original_limit


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

    response = client.post(
        "/api/strategies/backtest",
        json={"ids": ["strategy-1"], "account_margin": 25000},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["queued"] == 1
    assert body["runs"][0]["id"] == "run-1"
    runs_repo.create_queued_runs.assert_awaited_once()
    kwargs = runs_repo.create_queued_runs.await_args.kwargs
    assert kwargs["account_margin"] == 25_000.0


@patch("brokerai.web.routes.backtest_runs.begin_ai_feedback_job", new_callable=AsyncMock)
@patch("brokerai.web.routes.backtest_runs.BacktestRunsRepository")
def test_request_ai_feedback_accepted(
    mock_repo_cls,
    mock_begin,
    client: TestClient,
) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = {
        "id": "run-1",
        "status": "completed",
        "ai_feedback": None,
    }
    mock_begin.return_value = {
        "id": "run-1",
        "status": "completed",
        "ai_feedback": {
            "status": "running",
            "model_id": "m1",
            "model_name": "gpt-4o",
            "reasoning_effort": "medium",
            "markdown": None,
            "error": None,
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": None,
            "usage": None,
        },
    }

    response = client.post("/api/backtest-runs/run-1/ai-feedback")

    assert response.status_code == 202
    assert response.json()["ai_feedback"]["status"] == "running"
    mock_begin.assert_awaited_once_with("run-1")


@patch("brokerai.web.routes.backtest_runs.BacktestRunsRepository")
def test_request_ai_feedback_rejects_non_completed(
    mock_repo_cls,
    client: TestClient,
) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = {"id": "run-1", "status": "running"}

    response = client.post("/api/backtest-runs/run-1/ai-feedback")

    assert response.status_code == 400
    assert "completed" in response.json()["detail"].lower()


@patch("brokerai.web.routes.backtest_runs.begin_ai_feedback_job", new_callable=AsyncMock)
@patch("brokerai.web.routes.backtest_runs.BacktestRunsRepository")
def test_request_ai_feedback_rejects_when_disabled(
    mock_repo_cls,
    mock_begin,
    client: TestClient,
) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = {"id": "run-1", "status": "completed"}
    mock_begin.side_effect = ValueError(
        "Enable AI feedback and select a model in Settings → Backtesting"
    )

    response = client.post("/api/backtest-runs/run-1/ai-feedback")

    assert response.status_code == 400
    assert "Enable AI feedback" in response.json()["detail"]
