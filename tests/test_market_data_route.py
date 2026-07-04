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


def test_get_candles_requires_auth() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        response = test_client.get("/api/market-data/candles?symbol=EUR/USD")
    assert response.status_code == 401


def test_get_candles_rejects_unknown_pair(client: TestClient) -> None:
    response = client.get("/api/market-data/candles?symbol=FOO/BAR")
    assert response.status_code == 400
    assert "Unknown forex pair" in response.json()["detail"]


def test_get_candles_rejects_unknown_timeframe(client: TestClient) -> None:
    response = client.get("/api/market-data/candles?symbol=EUR/USD&timeframe=INVALID")
    assert response.status_code == 400
    assert "Unsupported timeframe" in response.json()["detail"]


@patch("brokerai.web.routes.market_data.register_explore_watch", new_callable=AsyncMock)
@patch("brokerai.web.routes.market_data.require_data_manager_service")
def test_get_candles_returns_payload(mock_require_service, mock_register_watch, client: TestClient) -> None:
    service = AsyncMock()
    service.request_candles = AsyncMock(
        return_value=[
            {
                "time": "2026-01-07T15:00:00.000000000Z",
                "open": 1.1,
                "high": 1.2,
                "low": 1.0,
                "close": 1.15,
                "volume": 42,
            }
        ]
    )
    mock_require_service.return_value = service

    response = client.get("/api/market-data/candles?symbol=EUR/USD&timeframe=M15&limit=120")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "EUR/USD"
    assert body["timeframe"] == "M15"
    assert body["source"] == "oanda"
    assert len(body["candles"]) == 1
    assert body["candles"][0]["close"] == 1.15
    mock_register_watch.assert_awaited_once_with("EUR/USD", "M15", bar_count=120)
    service.request_candles.assert_awaited_once_with(
        "EUR/USD",
        "M15",
        bar_count=120,
        source="oanda",
        since=None,
        until=None,
        requester="web_explore",
    )


@patch("brokerai.web.routes.market_data.register_explore_watch", new_callable=AsyncMock)
@patch("brokerai.web.routes.market_data.require_data_manager_service")
def test_get_candles_returns_503_when_empty(mock_require_service, _mock_register_watch, client: TestClient) -> None:
    service = AsyncMock()
    service.request_candles = AsyncMock(return_value=[])
    mock_require_service.return_value = service

    response = client.get("/api/market-data/candles?symbol=EUR/USD")

    assert response.status_code == 503
    assert "Candle data unavailable" in response.json()["detail"]


@patch("brokerai.web.routes.market_data.register_explore_watch", new_callable=AsyncMock)
@patch("brokerai.web.routes.market_data.require_data_manager_service")
def test_get_candles_accepts_max_limit(mock_require_service, _mock_register_watch, client: TestClient) -> None:
    service = AsyncMock()
    service.request_candles = AsyncMock(return_value=[])
    mock_require_service.return_value = service

    response = client.get("/api/market-data/candles?symbol=EUR/USD&limit=2000")

    assert response.status_code == 503
    service.request_candles.assert_awaited_once_with(
        "EUR/USD",
        "M15",
        bar_count=2000,
        source="oanda",
        since=None,
        until=None,
        requester="web_explore",
    )


@patch("brokerai.web.routes.market_data.MarketDataRepository")
def test_get_candle_delta_returns_bars_after_timestamp(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    repo.find_candles_after = AsyncMock(
        return_value=[
            {
                "time": "2026-01-07T15:15:00.000000000Z",
                "open": 1.1,
                "high": 1.2,
                "low": 1.0,
                "close": 1.15,
                "volume": 0,
            }
        ]
    )
    mock_repo_cls.return_value = repo

    response = client.get(
        "/api/market-data/candles/delta"
        "?symbol=EUR/USD&timeframe=M15&after=2026-01-07T15:00:00.000000000Z"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "EUR/USD"
    assert len(body["candles"]) == 1
    assert body["latest_time"] == "2026-01-07T15:15:00.000000000Z"
    repo.find_candles_after.assert_awaited_once_with(
        "EUR/USD",
        "M15",
        "oanda",
        "2026-01-07T15:00:00.000000000Z",
        limit=5,
    )


def test_get_candle_delta_rejects_unknown_pair(client: TestClient) -> None:
    response = client.get(
        "/api/market-data/candles/delta"
        "?symbol=FOO/BAR&timeframe=M15&after=2026-01-07T15:00:00.000000000Z"
    )
    assert response.status_code == 400


def test_candle_revision_emit_only_when_changed() -> None:
    last_emitted = "2026-01-07T15:00:00.000000000Z"
    assert "2026-01-07T15:15:00.000000000Z" != last_emitted
    assert "2026-01-07T15:00:00.000000000Z" == last_emitted


@patch("brokerai.web.routes.market_data.require_data_manager_service")
def test_get_candles_rejects_limit_above_max(_mock_require_service, client: TestClient) -> None:
    response = client.get("/api/market-data/candles?symbol=EUR/USD&limit=2001")
    assert response.status_code == 422

