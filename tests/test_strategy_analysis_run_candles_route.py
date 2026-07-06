from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def _candles(count: int, *, end: datetime, timeframe: str = "M15") -> list[dict]:
    bar_duration = timeframe_to_duration(timeframe)
    rows: list[dict] = []
    for offset in range(count):
        opened = end - (bar_duration * (count - 1 - offset))
        rows.append(
            {
                "time": opened.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
                "open": 1.1,
                "high": 1.2,
                "low": 1.0,
                "close": 1.15,
                "volume": 42,
            }
        )
    return rows


def _m15_candles(count: int, *, end: datetime) -> list[dict]:
    return _candles(count, end=end, timeframe="M15")


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

    candle_time = datetime.fromisoformat("2026-01-01T00:15:00+00:00")
    analyzed_at = datetime.fromisoformat("2026-01-01T00:15:01+00:00")
    run = {**ANALYSIS_RUN, "analyzed_at": analyzed_at.isoformat()}
    repo.get_by_id.return_value = run

    warmup_bars = 63
    display_bars_before = max(ANALYSIS_DISPLAY_BARS_BEFORE, warmup_bars)
    bars_to_analyzed = int((analyzed_at - candle_time) / timeframe_to_duration("M15")) + 1
    tail_bars = max(ANALYSIS_DISPLAY_BARS_AFTER + 2, bars_to_analyzed)
    fetch_bars = display_bars_before + warmup_bars + tail_bars
    candles = _m15_candles(fetch_bars, end=candle_time)

    dm = AsyncMock()
    dm.fetch_live_candles_from_oanda = AsyncMock(return_value=candles)
    mock_require_service.return_value = dm

    response = client.get("/api/strategy-analysis-runs/run-1/candles")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "EUR/USD"
    assert body["timeframe"] == "M15"
    assert body["source"] == "oanda"
    assert body["price_side"] == "M"
    assert len(body["candles"]) == fetch_bars
    assert body["warmup_bars"] == 63

    bar_duration = timeframe_to_duration("M15")
    display_since = datetime.fromisoformat(body["display_since"])
    display_until = datetime.fromisoformat(body["display_until"])
    fetch_since = datetime.fromisoformat(body["since"])
    fetch_until = datetime.fromisoformat(body["until"])
    anchor_open = candle_time
    last_open = datetime.fromisoformat(candles[-1]["time"].replace("Z", "+00:00"))
    display_end_open = min(
        anchor_open + (bar_duration * ANALYSIS_DISPLAY_BARS_AFTER),
        last_open,
    )

    assert display_since == candle_time - (bar_duration * display_bars_before)
    assert display_until == display_end_open
    assert fetch_since == datetime.fromisoformat(candles[0]["time"].replace("Z", "+00:00"))
    assert fetch_until == datetime.fromisoformat(candles[-1]["time"].replace("Z", "+00:00")) + bar_duration

    dm.ensure_coverage.assert_not_called()
    dm.fetch_live_candles_from_oanda.assert_awaited_once()
    call = dm.fetch_live_candles_from_oanda.await_args
    assert call.args[0] == "EUR/USD"
    assert call.args[1] == "M15"
    assert call.args[2] == fetch_bars
    assert call.kwargs["until"] == candle_time


@patch("brokerai.web.routes.strategy_analysis_runs.require_data_manager_service")
@patch("brokerai.web.routes.strategy_analysis_runs.StrategyAnalysisRunsRepository")
def test_get_strategy_analysis_run_candles_anchors_on_crossover_metadata(
    mock_repo_cls,
    mock_require_service,
    client: TestClient,
) -> None:
    """Startup catchup runs keep crossover_time in metadata while candle_time is current."""
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    crossover_time = datetime(2026, 1, 1, 18, 0, tzinfo=timezone.utc)
    latest_time = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
    run = {
        **ANALYSIS_RUN,
        "timeframe": "H1",
        "candle_time": latest_time.isoformat(),
        "analyzed_at": (latest_time + timedelta(minutes=1)).isoformat(),
        "metadata": {
            "crossover_time": crossover_time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
            "catchup": True,
        },
    }
    repo.get_by_id.return_value = run

    analyzed_at = datetime.fromisoformat(run["analyzed_at"])

    warmup_bars = 63
    display_bars_before = max(ANALYSIS_DISPLAY_BARS_BEFORE, warmup_bars)
    bar_duration = timeframe_to_duration("H1")
    bars_to_analyzed = int((analyzed_at - crossover_time) / bar_duration) + 1
    fetch_bars = display_bars_before + warmup_bars + max(ANALYSIS_DISPLAY_BARS_AFTER + 2, bars_to_analyzed)
    candles = _candles(fetch_bars, end=crossover_time, timeframe="H1")

    dm = AsyncMock()
    dm.fetch_live_candles_from_oanda = AsyncMock(return_value=candles)
    mock_require_service.return_value = dm

    response = client.get("/api/strategy-analysis-runs/run-1/candles")

    assert response.status_code == 200
    body = response.json()
    display_since = datetime.fromisoformat(body["display_since"])
    display_until = datetime.fromisoformat(body["display_until"])
    last_open = datetime.fromisoformat(candles[-1]["time"].replace("Z", "+00:00"))
    display_end_open = min(
        crossover_time + (bar_duration * ANALYSIS_DISPLAY_BARS_AFTER),
        last_open,
    )

    assert display_since == crossover_time - (bar_duration * display_bars_before)
    assert display_until == display_end_open


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

    candle_time = datetime.fromisoformat("2026-01-01T00:15:00+00:00")
    analyzed_at = datetime.fromisoformat("2026-01-01T00:15:01+00:00")
    run = {**ANALYSIS_RUN, "min_candles": 0, "analyzed_at": analyzed_at.isoformat()}
    repo.get_by_id.return_value = run

    warmup_bars = 63
    display_bars_before = max(ANALYSIS_DISPLAY_BARS_BEFORE, warmup_bars)
    bars_to_analyzed = int((analyzed_at - candle_time) / timeframe_to_duration("M15")) + 1
    tail_bars = max(ANALYSIS_DISPLAY_BARS_AFTER + 2, bars_to_analyzed)
    fetch_bars = display_bars_before + warmup_bars + tail_bars
    candles = _m15_candles(fetch_bars, end=candle_time)

    dm = AsyncMock()
    dm.fetch_live_candles_from_oanda = AsyncMock(return_value=candles)
    mock_require_service.return_value = dm

    response = client.get("/api/strategy-analysis-runs/run-1/candles")

    assert response.status_code == 200
    body = response.json()
    assert body["warmup_bars"] >= 63

    bar_duration = timeframe_to_duration("M15")
    display_since = datetime.fromisoformat(body["display_since"])
    assert display_since == candle_time - (bar_duration * body["warmup_bars"])


@patch("brokerai.web.routes.strategy_analysis_runs.require_data_manager_service")
@patch("brokerai.web.routes.strategy_analysis_runs.StrategyAnalysisRunsRepository")
def test_get_strategy_analysis_run_candles_spans_weekend_by_bar_count(
    mock_repo_cls,
    mock_require_service,
    client: TestClient,
) -> None:
    """Display window uses bar indices, not wall-clock hours across forex closures."""
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    candle_time = datetime(2026, 7, 6, 3, 0, tzinfo=timezone.utc)
    analyzed_at = datetime(2026, 7, 6, 3, 15, 1, tzinfo=timezone.utc)
    run = {
        **ANALYSIS_RUN,
        "pair": "USD/JPY",
        "min_candles": 100,
        "candle_time": candle_time.isoformat(),
        "analyzed_at": analyzed_at.isoformat(),
    }
    repo.get_by_id.return_value = run

    warmup_bars = 100
    display_bars_before = max(ANALYSIS_DISPLAY_BARS_BEFORE, warmup_bars)
    bars_to_analyzed = int((analyzed_at - candle_time) / timeframe_to_duration("M15")) + 1
    fetch_bars = display_bars_before + warmup_bars + max(ANALYSIS_DISPLAY_BARS_AFTER + 2, bars_to_analyzed)
    candles = _m15_candles(fetch_bars, end=candle_time)

    dm = AsyncMock()
    dm.fetch_live_candles_from_oanda = AsyncMock(return_value=candles)
    mock_require_service.return_value = dm

    response = client.get("/api/strategy-analysis-runs/run-1/candles")

    assert response.status_code == 200
    body = response.json()
    assert len(body["candles"]) == fetch_bars
    assert body["warmup_bars"] == 100

    display_since = datetime.fromisoformat(body["display_since"])
    bar_duration = timeframe_to_duration("M15")
    assert display_since == candle_time - (bar_duration * display_bars_before)


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
    dm.fetch_live_candles_from_oanda = AsyncMock(return_value=[])
    mock_require_service.return_value = dm

    response = client.get("/api/strategy-analysis-runs/run-1/candles")

    assert response.status_code == 503
    assert "OANDA" in response.json()["detail"]
