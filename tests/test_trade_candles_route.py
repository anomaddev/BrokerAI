from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from brokerai.bots.data_manager.candle_schedule import timeframe_to_duration
from fastapi.testclient import TestClient

from brokerai.web.app import app
from brokerai.web.routes.auth import require_auth

CLOSED_TRADE = {
    "id": "trade-1",
    "pair": "EUR/USD",
    "timeframe": "M15",
    "direction": "long",
    "entry_price": 1.1,
    "exit_price": 1.12,
    "status": "closed",
    "state": "closed",
    "opened_at": "2026-07-01T10:00:00+00:00",
    "closed_at": "2026-07-01T12:00:00+00:00",
}

STRATEGY_CLOSED_TRADE = {
    **CLOSED_TRADE,
    "strategy_id": "strategy-1",
}

OPEN_TRADE = {
    **CLOSED_TRADE,
    "status": "open",
    "state": "open",
    "closed_at": None,
    "exit_price": None,
}

CANDLE_ROW = {
    "time": "2026-07-01T10:00:00.000000000Z",
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


def test_get_trade_candles_requires_auth() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        response = test_client.get("/api/trades/trade-1/candles")
    assert response.status_code == 401


@patch("brokerai.web.routes.trades.require_data_manager_service")
@patch("brokerai.web.routes.trades.BrokerStateService")
def test_get_trade_candles_returns_payload_for_closed_trade(
    mock_service_cls,
    mock_require_service,
    client: TestClient,
) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.get_lot_by_id.return_value = CLOSED_TRADE

    dm = AsyncMock()
    dm.fetch_candles_from_oanda = AsyncMock(return_value=[CANDLE_ROW])
    mock_require_service.return_value = dm

    response = client.get("/api/trades/trade-1/candles")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "EUR/USD"
    assert body["timeframe"] == "M15"
    assert body["source"] == "oanda"
    assert len(body["candles"]) == 1
    assert body["candles"][0]["close"] == 1.15

    since = datetime.fromisoformat(body["since"])
    until = datetime.fromisoformat(body["until"])
    opened = datetime.fromisoformat("2026-07-01T10:00:00+00:00")
    closed = datetime.fromisoformat("2026-07-01T12:00:00+00:00")
    assert since == opened - timedelta(hours=1)
    assert until == closed + timedelta(hours=1) + timeframe_to_duration("M15")
    assert body["display_since"] == (opened - timedelta(hours=1)).isoformat()
    assert body["display_until"] == (closed + timedelta(hours=1)).isoformat()
    assert body["warmup_bars"] == 0

    dm.fetch_candles_from_oanda.assert_awaited_once()
    args = dm.fetch_candles_from_oanda.await_args.args
    assert args[0] == "EUR/USD"
    assert args[1] == "M15"


@patch("brokerai.web.routes.trades.require_data_manager_service")
@patch("brokerai.web.routes.trades.StrategiesRepository")
@patch("brokerai.web.routes.trades.BrokerStateService")
def test_get_trade_candles_extends_since_for_strategy_warmup(
    mock_service_cls,
    mock_strategies_cls,
    mock_require_service,
    client: TestClient,
) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.get_lot_by_id.return_value = STRATEGY_CLOSED_TRADE

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

    response = client.get("/api/trades/trade-1/candles")

    assert response.status_code == 200
    body = response.json()
    assert body["warmup_bars"] >= 63

    opened = datetime.fromisoformat("2026-07-01T10:00:00+00:00")
    display_since = datetime.fromisoformat(body["display_since"])
    fetch_since = datetime.fromisoformat(body["since"])
    assert display_since == opened - timedelta(hours=1)
    assert fetch_since < display_since

    dm.fetch_candles_from_oanda.assert_awaited_once()


@patch("brokerai.web.routes.trades.require_data_manager_service")
@patch("brokerai.web.routes.trades.BrokerStateService")
def test_get_trade_candles_open_trade_ends_at_now(
    mock_service_cls,
    mock_require_service,
    client: TestClient,
) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.get_lot_by_id.return_value = OPEN_TRADE

    dm = AsyncMock()
    dm.fetch_candles_from_oanda = AsyncMock(return_value=[CANDLE_ROW])
    mock_require_service.return_value = dm

    before = datetime.now(timezone.utc)
    response = client.get("/api/trades/trade-1/candles")
    after = datetime.now(timezone.utc)

    assert response.status_code == 200
    body = response.json()
    display_until = datetime.fromisoformat(body["display_until"])
    until = datetime.fromisoformat(body["until"])
    assert before <= display_until <= after + timedelta(seconds=2)
    assert until == display_until + timeframe_to_duration("M15")


@patch("brokerai.web.routes.trades.BrokerStateService")
def test_get_trade_candles_returns_404(mock_service_cls, client: TestClient) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.get_lot_by_id.return_value = None

    response = client.get("/api/trades/missing/candles")

    assert response.status_code == 404


@patch("brokerai.web.routes.trades.require_data_manager_service")
@patch("brokerai.web.routes.trades.BrokerStateService")
def test_get_trade_candles_returns_503_when_empty(
    mock_service_cls,
    mock_require_service,
    client: TestClient,
) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.get_lot_by_id.return_value = CLOSED_TRADE

    dm = AsyncMock()
    dm.fetch_candles_from_oanda = AsyncMock(return_value=[])
    mock_require_service.return_value = dm

    response = client.get("/api/trades/trade-1/candles")

    assert response.status_code == 503
    assert "OANDA" in response.json()["detail"]
