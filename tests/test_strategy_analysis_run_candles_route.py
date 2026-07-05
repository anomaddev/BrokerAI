from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from brokerai.bots.data_manager.candle_schedule import timeframe_to_duration
from fastapi.testclient import TestClient

from brokerai.web.app import app
from brokerai.web.routes.auth import require_auth
from brokerai.web.routes.strategy_analysis_runs import (
    ANALYSIS_DISPLAY_BARS_AFTER,
    ANALYSIS_DISPLAY_BARS_BEFORE,
)

ANALYSIS_RUN = {
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

CANDLE_ROW = {
    "time": "2026-01-01T00:15:00.000000000Z",
    "open": 1.1,
    "high": 1.2,
    "low": 1.0,
    "close": 1.15,
    "volume": 42,
}


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[require_auth] = lambda: "test-user"
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_get_strategy_analysis_run_candles_requires_auth() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        response = test_client.get("/api/strategy-analysis-runs/run-1/candles")
    assert response.status_code == 401


@patch("brokerai.web.routes.strategy_analysis_runs.require_data_manager_service")
@patch("brokerai.web.routes.strategy_analysis_runs.StrategyAnalysisRunsRepository")
def test_get_strategy_analysis_run_candles_returns_payload(
    mock_repo_cls,
    mock_require_service,
    client: TestClient,
) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = ANALYSIS_RUN

    dm = AsyncMock()
    dm.fetch_candles_from_oanda = AsyncMock(return_value=[CANDLE_ROW])
    mock_require_service.return_value = dm

    response = client.get("/api/strategy-analysis-runs/run-1/candles")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "EUR/USD"
    assert body["timeframe"] == "M15"
    assert body["source"] == "oanda"
    assert body["price_side"] == "M"
    assert len(body["candles"]) == 1
    assert body["warmup_bars"] == 63

    candle_time = datetime.fromisoformat("2026-01-01T00:15:00+00:00")
    bar_duration = timeframe_to_duration("M15")
    display_since = datetime.fromisoformat(body["display_since"])
    display_until = datetime.fromisoformat(body["display_until"])
    fetch_since = datetime.fromisoformat(body["since"])
    fetch_until = datetime.fromisoformat(body["until"])

    assert display_since == candle_time - (bar_duration * 63)
    assert display_until == candle_time + (bar_duration * (ANALYSIS_DISPLAY_BARS_AFTER + 1))
    assert fetch_since == candle_time - (bar_duration * (63 + 63))
    assert fetch_until == display_until + bar_duration

    dm.fetch_candles_from_oanda.assert_awaited_once()
    args = dm.fetch_candles_from_oanda.await_args.args
    assert args[0] == "EUR/USD"
    assert args[1] == "M15"
    assert dm.fetch_candles_from_oanda.await_args.kwargs["price"] == "M"


@patch("brokerai.web.routes.strategy_analysis_runs.require_data_manager_service")
@patch("brokerai.web.routes.strategy_analysis_runs.StrategiesRepository")
@patch("brokerai.web.routes.strategy_analysis_runs.StrategyAnalysisRunsRepository")
def test_get_strategy_analysis_run_candles_resolves_warmup_from_strategy(
    mock_repo_cls,
    mock_strategies_cls,
    mock_require_service,
    client: TestClient,
) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    run = {**ANALYSIS_RUN, "min_candles": 0}
    repo.get_by_id.return_value = run

    strategies_repo = AsyncMock()
    mock_strategies_cls.return_value = strategies_repo
    strategies_repo.get_by_id.return_value = {
        "id": "strategy-1",
        "preset_id": "ema_crossover",
        "params": {"min_candles": 63, "timeframe": "M15"},
    }

    dm = AsyncMock()
    dm.fetch_candles_from_oanda = AsyncMock(return_value=[CANDLE_ROW])
    mock_require_service.return_value = dm

    response = client.get("/api/strategy-analysis-runs/run-1/candles")

    assert response.status_code == 200
    body = response.json()
    assert body["warmup_bars"] >= 63

    candle_time = datetime.fromisoformat("2026-01-01T00:15:00+00:00")
    bar_duration = timeframe_to_duration("M15")
    display_since = datetime.fromisoformat(body["display_since"])
    assert display_since == candle_time - (bar_duration * body["warmup_bars"])


@patch("brokerai.web.routes.strategy_analysis_runs.StrategyAnalysisRunsRepository")
def test_get_strategy_analysis_run_candles_returns_404(
    mock_repo_cls,
    client: TestClient,
) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = None

    response = client.get("/api/strategy-analysis-runs/missing/candles")

    assert response.status_code == 404


@patch("brokerai.web.routes.strategy_analysis_runs.require_data_manager_service")
@patch("brokerai.web.routes.strategy_analysis_runs.StrategyAnalysisRunsRepository")
def test_get_strategy_analysis_run_candles_returns_503_when_empty(
    mock_repo_cls,
    mock_require_service,
    client: TestClient,
) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = ANALYSIS_RUN

    dm = AsyncMock()
    dm.fetch_candles_from_oanda = AsyncMock(return_value=[])
    mock_require_service.return_value = dm

    response = client.get("/api/strategy-analysis-runs/run-1/candles")

    assert response.status_code == 503
    assert "OANDA" in response.json()["detail"]
