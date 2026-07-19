from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokerai.auth.supabase_auth import (
    admin_create_user,
    admin_update_user_profile,
    build_profile_user_metadata,
)


def test_build_profile_user_metadata_uses_first_name_as_display():
    assert build_profile_user_metadata(
        username="admin",
        first_name="Jordan",
        last_name="Belfort",
    ) == {
        "username": "admin",
        "first_name": "Jordan",
        "last_name": "Belfort",
        "full_name": "Jordan",
        "name": "Jordan",
    }


def _mock_settings(monkeypatch) -> None:
    monkeypatch.setenv("BROKERAI_SUPABASE_URL", "http://supabase.test")
    monkeypatch.setenv("BROKERAI_SUPABASE_SERVICE_ROLE_KEY", "service-role")
    from brokerai.config.settings import reload_settings

    reload_settings()


def _mock_client(response_json: dict) -> AsyncMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = response_json
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.put = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_admin_create_user_includes_name_metadata(monkeypatch):
    _mock_settings(monkeypatch)
    mock_client = _mock_client({"id": "user-1"})

    with patch("brokerai.auth.supabase_auth.httpx.AsyncClient", return_value=mock_client):
        result = await admin_create_user(
            email="admin@example.com",
            password="BrokerAI!2026Password",
            username="admin",
            first_name="Jordan",
            last_name="Belfort",
        )

    assert result["id"] == "user-1"
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["user_metadata"]["full_name"] == "Jordan"
    assert payload["user_metadata"]["name"] == "Jordan"
    assert payload["user_metadata"]["first_name"] == "Jordan"
    assert payload["user_metadata"]["last_name"] == "Belfort"
    assert payload["app_metadata"] == {"username": "admin", "role": "admin"}


@pytest.mark.asyncio
async def test_admin_update_user_profile_replaces_metadata(monkeypatch):
    _mock_settings(monkeypatch)
    mock_client = _mock_client({"id": "user-1"})

    with patch("brokerai.auth.supabase_auth.httpx.AsyncClient", return_value=mock_client):
        await admin_update_user_profile(
            user_id="user-1",
            username="admin",
            first_name="Donnie",
            last_name="Azoff",
        )

    assert mock_client.put.call_args.args[0].endswith("/auth/v1/admin/users/user-1")
    payload = mock_client.put.call_args.kwargs["json"]
    assert payload["user_metadata"] == {
        "username": "admin",
        "first_name": "Donnie",
        "last_name": "Azoff",
        "full_name": "Donnie",
        "name": "Donnie",
    }
