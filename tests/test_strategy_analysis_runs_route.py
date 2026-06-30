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


def test_list_strategy_analysis_runs_requires_auth() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        response = test_client.get("/api/strategy-analysis-runs")
    assert response.status_code == 401


@patch("brokerai.web.routes.strategy_analysis_runs.StrategyAnalysisRunsRepository")
def test_list_strategy_analysis_runs_returns_payload(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.list_recent.return_value = [
        {
            "id": "run-1",
            "strategy_id": "strategy-1",
            "strategy_name": "Test",
            "pair": "EUR/USD",
            "timeframe": "M15",
            "direction": "long",
            "confidence": 0.8,
            "signal_type": "ema_crossover",
            "min_candles": 63,
            "metadata": {},
            "candle_time": "2026-01-01T00:15:00+00:00",
            "analyzed_at": "2026-01-01T00:15:01+00:00",
            "run_type": "live",
            "execution": None,
        }
    ]

    response = client.get("/api/strategy-analysis-runs?strategy_id=strategy-1&pair=EUR/USD&limit=25")

    assert response.status_code == 200
    body = response.json()
    assert body["latest"]["id"] == "run-1"
    assert len(body["runs"]) == 1
    repo.list_recent.assert_awaited_once_with(
        strategy_id="strategy-1",
        pair="EUR/USD",
        limit=25,
        before=None,
    )


@patch("brokerai.web.routes.strategy_analysis_runs.StrategyAnalysisRunsRepository")
def test_get_strategy_analysis_run_returns_detail(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = {
        "id": "run-1",
        "strategy_id": "strategy-1",
        "strategy_name": "Test",
        "pair": "EUR/USD",
        "timeframe": "M15",
        "direction": None,
        "confidence": 0.0,
        "signal_type": "ema_crossover",
        "min_candles": 63,
        "metadata": {"signal": "none"},
        "candle_time": "2026-01-01T00:15:00+00:00",
        "analyzed_at": "2026-01-01T00:15:01+00:00",
        "run_type": "live",
        "execution": {
            "processed_at": "2026-01-01T00:15:02+00:00",
            "gates_passed": False,
            "gate_reasons": ["no_signal"],
            "priority_winner": False,
            "intent_queued": False,
            "intent": None,
        },
    }

    response = client.get("/api/strategy-analysis-runs/run-1")

    assert response.status_code == 200
    assert response.json()["execution"]["gate_reasons"] == ["no_signal"]


@patch("brokerai.web.routes.strategy_analysis_runs.StrategyAnalysisRunsRepository")
def test_get_strategy_analysis_run_not_found(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = None

    response = client.get("/api/strategy-analysis-runs/missing")

    assert response.status_code == 404
