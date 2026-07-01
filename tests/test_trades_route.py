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


@patch("brokerai.web.routes.trades.TradesRepository")
def test_list_trades_returns_payload(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.list_trades.return_value = [
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
    repo.list_trades.assert_awaited_once()


@patch("brokerai.web.routes.trades.TradesRepository")
def test_list_trades_all_status(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.list_trades.return_value = [
        {"id": "open-1", "status": "open"},
        {"id": "closed-1", "status": "closed"},
    ]

    response = client.get("/api/trades?status=all&limit=50")

    assert response.status_code == 200
    body = response.json()
    assert len(body["trades"]) == 2
    repo.list_trades.assert_awaited_once_with(
        status="all",
        strategy_id=None,
        pair=None,
        limit=50,
        before=None,
    )


@patch("brokerai.web.routes.trades.TradesRepository")
def test_close_trade_returns_404(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = None

    response = client.post("/api/trades/missing/close")

    assert response.status_code == 404


@patch("brokerai.web.routes.trades.TradesRepository")
def test_close_trade_rejects_closed(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = {"id": "trade-1", "status": "closed"}

    response = client.post("/api/trades/trade-1/close")

    assert response.status_code == 400
    repo.close_trade.assert_not_awaited()


@patch("brokerai.web.routes.trades.TradesRepository")
def test_close_trade_without_broker(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.side_effect = [
        {"id": "trade-1", "status": "open", "broker_order_id": None},
        {"id": "trade-1", "status": "closed", "close_reason": "manual_close"},
    ]

    response = client.post("/api/trades/trade-1/close")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "closed"
    repo.close_trade.assert_awaited_once_with(
        "trade-1",
        reason="manual_close",
        metadata={},
    )


@patch("brokerai.web.routes.trades.TradesRepository")
def test_get_trade_returns_404(mock_repo_cls, client: TestClient) -> None:
    repo = AsyncMock()
    mock_repo_cls.return_value = repo
    repo.get_by_id.return_value = None

    response = client.get("/api/trades/missing")

    assert response.status_code == 404


@patch("brokerai.web.routes.trades.get_broker_open_trades_snapshot")
@patch("brokerai.web.routes.trades.TradesRepository")
@patch("brokerai.web.routes.trades.ExchangeConnectionsRepository")
def test_reconciliation_unconfigured(
    mock_exchange_cls,
    mock_repo_cls,
    mock_snapshot,
    client: TestClient,
) -> None:
    trades_repo = AsyncMock()
    mock_repo_cls.return_value = trades_repo
    trades_repo.list_trades.return_value = []

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
