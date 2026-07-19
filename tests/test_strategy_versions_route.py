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


@patch("brokerai.web.routes.strategies.StrategyVersionsRepository")
@patch("brokerai.web.routes.strategies.StrategiesRepository")
def test_list_strategy_versions_returns_payload(
    mock_strategies_cls,
    mock_versions_cls,
    client: TestClient,
) -> None:
    strategies = AsyncMock()
    versions_repo = AsyncMock()
    mock_strategies_cls.return_value = strategies
    mock_versions_cls.return_value = versions_repo
    strategies.get_by_id.return_value = {"id": "s1", "name": "EMA"}
    versions_repo.list_for_strategy.return_value = (
        [
            {
                "id": "v2",
                "strategy_id": "s1",
                "version": 2,
                "created_at": "2026-07-18T12:00:00+00:00",
                "change_label": "EMA parameters updated",
            }
        ],
        1,
    )

    response = client.get("/api/strategies/s1/versions?limit=20&offset=0")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["versions"][0]["id"] == "v2"
    versions_repo.list_for_strategy.assert_awaited_once_with("s1", limit=20, offset=0)


@patch("brokerai.web.routes.strategies.StrategiesRepository")
def test_list_strategy_versions_not_found(mock_strategies_cls, client: TestClient) -> None:
    strategies = AsyncMock()
    mock_strategies_cls.return_value = strategies
    strategies.get_by_id.return_value = None

    response = client.get("/api/strategies/missing/versions")
    assert response.status_code == 404


@patch("brokerai.web.routes.strategies.StrategyVersionsRepository")
@patch("brokerai.web.routes.strategies.StrategiesRepository")
def test_get_strategy_version_returns_snapshot(
    mock_strategies_cls,
    mock_versions_cls,
    client: TestClient,
) -> None:
    strategies = AsyncMock()
    versions_repo = AsyncMock()
    mock_strategies_cls.return_value = strategies
    mock_versions_cls.return_value = versions_repo
    strategies.get_by_id.return_value = {"id": "s1", "name": "EMA"}
    versions_repo.get_by_id.return_value = {
        "id": "v1",
        "strategy_id": "s1",
        "version": 1,
        "created_at": "2026-07-18T12:00:00+00:00",
        "change_label": "Created strategy",
        "snapshot": {
            "name": "EMA",
            "description": "",
            "params": {"timeframe": "M15"},
            "instrument_selection": {"forex": ["EUR/USD"]},
            "enabled": False,
            "preset_id": "ema_crossover",
        },
    }

    response = client.get("/api/strategies/s1/versions/v1")

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["name"] == "EMA"
    versions_repo.get_by_id.assert_awaited_once_with("s1", "v1")


@patch("brokerai.web.routes.strategies.StrategyVersionsRepository")
@patch("brokerai.web.routes.strategies.StrategiesRepository")
def test_get_strategy_version_not_found(
    mock_strategies_cls,
    mock_versions_cls,
    client: TestClient,
) -> None:
    strategies = AsyncMock()
    versions_repo = AsyncMock()
    mock_strategies_cls.return_value = strategies
    mock_versions_cls.return_value = versions_repo
    strategies.get_by_id.return_value = {"id": "s1"}
    versions_repo.get_by_id.return_value = None

    response = client.get("/api/strategies/s1/versions/missing")
    assert response.status_code == 404
