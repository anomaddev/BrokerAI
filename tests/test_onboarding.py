from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from brokerai.auth import hash_password
from brokerai.auth.onboarding import OnboardingStore
from brokerai.auth.store import AuthStore
from brokerai.config.settings import reload_settings
from brokerai.web.app import app

PASSWORD = "BrokerAI!2026Password"


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("BROKERAI_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BROKERAI_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("BROKERAI_AUTH_MODE", "builtin")
    monkeypatch.setenv("BROKERAI_USE_POSTGRES", "false")
    reload_settings()
    return TestClient(app)


def test_onboarding_status_before_admin(client: TestClient):
    response = client.get("/api/onboarding/status")
    assert response.status_code == 200
    body = response.json()
    assert body["auth_complete"] is False
    assert body["onboarding_complete"] is False
    assert body["current_step"] == "admin"


def test_create_user_seeds_exchange_step(client: TestClient):
    store = AuthStore()
    store.create_user("admin", hash_password(PASSWORD))
    status = client.get("/api/onboarding/status").json()
    assert status["auth_complete"] is True
    assert status["onboarding_complete"] is False
    assert status["current_step"] == "exchange"


def test_legacy_admin_without_onboarding_file_is_complete(client: TestClient):
    """Existing installs (admin, no onboarding.json) must not be forced into the wizard."""
    store = AuthStore()
    store.ensure_dir()
    store.users_path.write_text(
        '{"username": "admin", "password_hash": "x", "created_at": "2020-01-01T00:00:00+00:00"}'
    )
    (store.auth_dir / "setup_complete").touch()
    assert not OnboardingStore().path.exists()
    status = client.get("/api/onboarding/status").json()
    assert status["auth_complete"] is True
    assert status["onboarding_complete"] is True


def test_progress_and_complete_flow(client: TestClient):
    setup = client.post(
        "/api/auth/setup",
        data={
            "first_name": "Admin",
            "last_name": "User",
            "email": "admin@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert setup.status_code == 200

    progress = client.put(
        "/api/onboarding/progress",
        json={
            "current_step": "instruments",
            "selected_exchange_id": "oanda",
        },
    )
    assert progress.status_code == 200
    assert progress.json()["current_step"] == "instruments"
    assert progress.json()["selected_exchange_id"] == "oanda"

    progress = client.put(
        "/api/onboarding/progress",
        json={
            "current_step": "data_sources",
            "enabled_pairs": ["EUR/USD", "GBP/USD"],
        },
    )
    assert progress.status_code == 200
    assert progress.json()["enabled_pairs"] == ["EUR/USD", "GBP/USD"]
    assert progress.json()["current_step"] == "data_sources"

    progress = client.put(
        "/api/onboarding/progress",
        json={"current_step": "models"},
    )
    assert progress.status_code == 200
    assert progress.json()["current_step"] == "models"

    progress = client.put(
        "/api/onboarding/progress",
        json={"current_step": "finish"},
    )
    assert progress.status_code == 200

    done = client.post("/api/onboarding/complete")
    assert done.status_code == 200
    assert done.json()["onboarding_complete"] is True

    blocked = client.put("/api/onboarding/progress", json={"current_step": "exchange"})
    assert blocked.status_code == 409


def test_complete_allows_skipped_optional_steps(client: TestClient):
    setup = client.post(
        "/api/auth/setup",
        data={
            "first_name": "Admin",
            "last_name": "User",
            "email": "admin@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert setup.status_code == 200
    verify = client.post("/api/onboarding/verify")
    assert verify.status_code == 200
    assert verify.json()["verified"] is True
    assert verify.json()["current_step"] == "finish"
    response = client.post("/api/onboarding/complete")
    assert response.status_code == 200
    assert response.json()["onboarding_complete"] is True


def test_setup_and_profile_use_first_last_name(client: TestClient, monkeypatch):
    setup = client.post(
        "/api/auth/setup",
        data={
            "first_name": "Jordan",
            "last_name": "Belfort",
            "email": "jordan@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    )
    assert setup.status_code == 200

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["display_name"] == "Jordan"
    assert me.json()["first_name"] == "Jordan"
    assert me.json()["last_name"] == "Belfort"

    # Simulate a Supabase-linked profile so account updates mirror Auth metadata.
    store = AuthStore()
    user = store.get_user()
    assert user is not None
    store._save_user(user.replace(oidc_sub="supabase-user-1"))

    monkeypatch.setenv("BROKERAI_SUPABASE_URL", "http://supabase.test")
    monkeypatch.setenv("BROKERAI_SUPABASE_SERVICE_ROLE_KEY", "service-role")
    reload_settings()

    from unittest.mock import AsyncMock, patch

    with patch(
        "brokerai.auth.supabase_auth.admin_update_user_profile",
        new_callable=AsyncMock,
    ) as sync:
        updated = client.put(
            "/api/auth/account/profile",
            json={"first_name": "Donnie", "last_name": "Azoff"},
        )
        assert updated.status_code == 200
        assert updated.json()["display_name"] == "Donnie"
        assert updated.json()["first_name"] == "Donnie"
        assert updated.json()["last_name"] == "Azoff"
        sync.assert_awaited_once()
        assert sync.await_args.kwargs["first_name"] == "Donnie"
        assert sync.await_args.kwargs["last_name"] == "Azoff"
        assert sync.await_args.kwargs["username"] == "jordan"

    me = client.get("/api/auth/me")
    assert me.json()["display_name"] == "Donnie"


def test_onboarding_store_reset(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("BROKERAI_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BROKERAI_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("BROKERAI_USE_POSTGRES", "false")
    reload_settings()
    store = OnboardingStore()
    store.init_after_admin()
    assert store.path.exists()
    store.reset()
    assert not store.path.exists()
