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


def test_list_trades_requires_auth() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        response = test_client.get("/api/trades")
    assert response.status_code == 401


@patch("brokerai.web.routes.trades.BrokerStateService")
def test_list_trades_returns_payload(mock_service_cls, client: TestClient) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.list_lots.return_value = [
        {
            "id": "trade-1",
            "strategy_id": "s1",
            "strategy_name": "EMA",
            "pair": "EUR/USD",
            "asset_class": "forex",
            "direction": "long",
            "entry_price": 1.1,
            "stop_loss": 1.09,
            "take_profit": 1.12,
            "exit_mode": "rr_ratio",
            "risk_pct": 1.0,
            "units": 1000,
            "confidence": 0.8,
            "status": "open",
            "broker_order_id": "123",
            "metadata": {},
            "opened_at": "2026-06-30T12:00:00+00:00",
            "closed_at": None,
        }
    ]

    response = client.get("/api/trades?status=open&strategy_id=s1&pair=EUR/USD&limit=25")

    assert response.status_code == 200
    body = response.json()
    assert body["latest"]["id"] == "trade-1"
    assert len(body["trades"]) == 1
    service.list_lots.assert_awaited_once()


@patch("brokerai.web.routes.trades.BrokerStateService")
def test_list_trades_all_status(mock_service_cls, client: TestClient) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.list_lots.return_value = [
        {"id": "open-1", "status": "open"},
        {"id": "closed-1", "status": "closed"},
    ]

    response = client.get("/api/trades?status=all&limit=50")

    assert response.status_code == 200
    body = response.json()
    assert len(body["trades"]) == 2
    service.list_lots.assert_awaited_once_with(
        state="all",
        strategy_id=None,
        pair=None,
        limit=50,
        before=None,
        exchange_id="oanda",
    )


@patch("brokerai.web.routes.trades.BrokerStateService")
def test_close_trade_returns_404(mock_service_cls, client: TestClient) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.get_lot_by_id.return_value = None

    response = client.post("/api/trades/missing/close")

    assert response.status_code == 404


@patch("brokerai.web.routes.trades.BrokerStateService")
def test_close_trade_rejects_closed(mock_service_cls, client: TestClient) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.get_lot_by_id.return_value = {"id": "trade-1", "status": "closed", "state": "closed"}

    response = client.post("/api/trades/trade-1/close")

    assert response.status_code == 400
    service.close_lot.assert_not_awaited()


@patch("brokerai.web.routes.trades.BrokerStateService")
def test_close_trade_without_broker(mock_service_cls, client: TestClient) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.get_lot_by_id.return_value = {
        "id": "trade-1",
        "status": "open",
        "state": "open",
        "exchange_id": "oanda",
        "broker_lot_id": None,
    }
    service.close_lot.return_value = {
        "id": "trade-1",
        "status": "closed",
        "state": "closed",
        "close_reason": "manual_close",
    }

    response = client.post("/api/trades/trade-1/close")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "closed"
    service.close_lot.assert_awaited_once_with("oanda", "trade-1", reason="manual_close")


@patch("brokerai.web.routes.trades.ExchangeConnectionsRepository")
@patch("brokerai.web.routes.trades.OandaAdapter")
@patch("brokerai.web.routes.trades.BrokerStateService")
def test_debug_trade_row_logs_to_server(
    mock_service_cls,
    mock_adapter_cls,
    mock_exchange_cls,
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.INFO)

    service = AsyncMock()
    mock_service_cls.return_value = service
    service.get_lot_by_id.return_value = {
        "id": "trade-1",
        "status": "open",
        "state": "open",
        "broker_lot_id": "565",
        "pair": "EUR/JPY",
        "direction": "short",
    }

    exchange_repo = AsyncMock()
    mock_exchange_cls.return_value = exchange_repo
    exchange_repo.get_oanda.return_value = {
        "access_token": "token",
        "account_id": "acct",
        "environment": "practice",
    }

    adapter = AsyncMock()
    mock_adapter_cls.return_value = adapter
    adapter.fetch_open_lots_with_prices.return_value = [
        type("Lot", (), {"broker_lot_id": "565"})(),
    ]

    response = client.post("/api/trades/trade-1/debug")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["broker_lot_id"] == "565"
    assert body["live_on_broker"] is True
    assert any("Trade row click" in record.message for record in caplog.records)


@patch("brokerai.web.routes.trades.ExchangeConnectionsRepository")
@patch("brokerai.web.routes.trades.OandaAdapter")
@patch("brokerai.web.routes.trades.BrokerStateService")
def test_debug_trade_row_returns_404_when_missing(
    mock_service_cls,
    mock_adapter_cls,
    mock_exchange_cls,
    client: TestClient,
) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.get_lot_by_id.return_value = None

    response = client.post("/api/trades/missing-id/debug")

    assert response.status_code == 404


@patch("brokerai.web.routes.trades.BrokerStateService")
def test_get_trade_returns_404(mock_service_cls, client: TestClient) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.get_lot_by_id.return_value = None

    response = client.get("/api/trades/missing")

    assert response.status_code == 404


@patch("brokerai.web.routes.trades.start_trade_sync_task")
def test_sync_trades_starts_background_task(mock_start, client: TestClient) -> None:
    mock_start.return_value = ("task-123", None)

    response = client.post("/api/trades/sync")

    assert response.status_code == 202
    body = response.json()
    assert body["task_id"] == "task-123"
    assert body["status"] == "accepted"
    mock_start.assert_awaited_once()


@patch("brokerai.web.routes.trades.start_trade_sync_task")
def test_sync_trades_conflict(mock_start, client: TestClient) -> None:
    mock_start.return_value = (None, "A task is already running: Sync OANDA trades")

    response = client.post("/api/trades/sync")

    assert response.status_code == 409
    assert response.json()["skipped_reason"] == "A task is already running: Sync OANDA trades"


@patch("brokerai.web.routes.trades.OandaAdapter")
@patch("brokerai.web.routes.trades.BrokerStateService")
@patch("brokerai.web.routes.trades.ExchangeConnectionsRepository")
def test_reconciliation_unconfigured(
    mock_exchange_cls,
    mock_service_cls,
    mock_adapter_cls,
    client: TestClient,
) -> None:
    service = AsyncMock()
    mock_service_cls.return_value = service
    service.list_lots.return_value = []

    exchange_repo = AsyncMock()
    mock_exchange_cls.return_value = exchange_repo
    exchange_repo.get_oanda.return_value = {
        "access_token": "",
        "account_id": "",
        "environment": "practice",
    }

    response = client.get("/api/trades/reconciliation")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["status"] == "unconfigured"
