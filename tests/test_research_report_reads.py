from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from brokerai.db.repositories.research_report_reads import (
    is_countable_report_type,
    is_unread,
    unread_group,
)
from brokerai.web.app import app
from brokerai.web.routes.auth import require_auth


def test_is_unread_missing_entry() -> None:
    assert is_unread("daily", "a.md", "t1", {}) is True


def test_is_unread_matching_generated_at() -> None:
    reads = {"a.md": {"read_at": "x", "generated_at": "t1"}}
    assert is_unread("daily", "a.md", "t1", reads) is False


def test_is_unread_regenerated() -> None:
    reads = {"a.md": {"read_at": "x", "generated_at": "t1"}}
    assert is_unread("daily", "a.md", "t2", reads) is True


def test_daily_model_is_countable() -> None:
    assert is_countable_report_type("daily_model") is True
    assert unread_group("daily_model") == "daily"
    assert unread_group("weekly_brief") == "weekly"
    assert is_unread("daily_model", "m.md", None, {}) is True


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[require_auth] = lambda: "test-user"
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@patch("brokerai.web.routes.research.count_unread_reports", new_callable=AsyncMock)
def test_unread_count_route(mock_count, client: TestClient) -> None:
    mock_count.return_value = {"unread_count": 3, "daily": 2, "weekly": 1}
    response = client.get("/api/research/reports/unread-count")
    assert response.status_code == 200
    assert response.json() == {"unread_count": 3, "daily": 2, "weekly": 1}
    mock_count.assert_awaited_once_with("test-user")


@patch("brokerai.web.routes.research.mark_report_read", new_callable=AsyncMock)
def test_mark_read_route(mock_mark, client: TestClient) -> None:
    mock_mark.return_value = {
        "ok": True,
        "filename": "2026_29/2026-07-18-daily.md",
        "unread_count": 1,
        "daily": 1,
        "weekly": 0,
    }
    response = client.post(
        "/api/research/reports/mark-read",
        params={"filename": "2026_29/2026-07-18-daily.md"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    mock_mark.assert_awaited_once()


@patch("brokerai.web.routes.research.list_report_entries", new_callable=AsyncMock)
def test_list_reports_awaits_entries(mock_list, client: TestClient) -> None:
    mock_list.return_value = [
        {
            "filename": "x.md",
            "date": "2026-07-18",
            "type": "daily",
            "path": "x.md",
            "model_label": None,
            "generated_at": None,
            "reasoning_effort": None,
            "size_bytes": 1,
            "is_read": False,
        }
    ]
    response = client.get("/api/research/reports")
    assert response.status_code == 200
    body = response.json()
    assert body["reports"][0]["is_read"] is False
    mock_list.assert_awaited_once()
