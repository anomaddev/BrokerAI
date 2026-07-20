from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from brokerai.auth import SessionManager, hash_password
from brokerai.auth.oidc_client import parse_oidc_claims, username_from_oidc_claims
from brokerai.auth.store import AuthStore
from brokerai.config.settings import Settings, get_settings, reload_settings
from brokerai.web.app import app


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("BROKERAI_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BROKERAI_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("BROKERAI_AUTH_MODE", "builtin")
    reload_settings()
    return TestClient(app)


@pytest.fixture
def oidc_settings(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("BROKERAI_DATA_DIR", str(data_dir))
    monkeypatch.setenv("BROKERAI_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("BROKERAI_AUTH_MODE", "oidc")
    monkeypatch.setenv("BROKERAI_OIDC_ISSUER", "https://auth.example.com")
    monkeypatch.setenv("BROKERAI_OIDC_CLIENT_ID", "brokerai")
    monkeypatch.setenv("BROKERAI_OIDC_CLIENT_SECRET", "secret")
    reload_settings()
    return get_settings()


def test_auth_config_builtin(auth_client: TestClient):
    response = auth_client.get("/api/auth/config")
    assert response.status_code == 200
    assert response.json() == {
        "mode": "builtin",
        "setup_complete": False,
        "mfa_available": False,
        "supabase_configured": False,
    }


def test_login_setup_rejected_in_oidc_mode(oidc_settings: Settings):
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"username": "admin", "password": "x"})
    assert response.status_code == 409


def test_session_manager_roundtrip_with_oidc_sub():
    manager = SessionManager(Settings(secret_key="test-secret"))
    token = manager.create_token("admin", oidc_sub="sub-123")
    verified = manager.verify_token(token)
    assert verified == ("admin", "sub-123")


def test_username_from_oidc_claims_prefers_preferred_username():
    assert username_from_oidc_claims({"preferred_username": "trader-1", "sub": "abc"}) == "trader-1"


def test_parse_oidc_claims_extracts_names():
    claims = parse_oidc_claims(
        {
            "sub": "user-1",
            "preferred_username": "trader",
            "given_name": "Pat",
            "family_name": "Lee",
            "email": "pat@example.com",
        }
    )
    assert claims.sub == "user-1"
    assert claims.username == "trader"
    assert claims.first_name == "Pat"
    assert claims.last_name == "Lee"
    assert claims.email == "pat@example.com"


def test_create_or_link_oidc_user_creates_profile(oidc_settings: Settings):
    store = AuthStore(oidc_settings)
    record = store.create_or_link_oidc_user(
        oidc_sub="oidc-sub-1",
        username="trader",
        first_name="Pat",
        last_name="Lee",
    )
    assert record.username == "trader"
    assert record.oidc_sub == "oidc-sub-1"
    assert record.password_hash is None
    assert store.is_setup_complete()


def test_create_or_link_oidc_user_links_existing_profile(oidc_settings: Settings):
    store = AuthStore(oidc_settings)
    store.create_user("admin", hash_password("BrokerAI!2026Password"))
    record = store.create_or_link_oidc_user(
        oidc_sub="oidc-sub-1",
        username="ignored",
        first_name="Pat",
        last_name=None,
        email="pat@example.com",
    )
    assert record.username == "admin"
    assert record.oidc_sub == "oidc-sub-1"
    assert record.email == "pat@example.com"


def test_create_or_link_oidc_user_reconciles_identity_on_relogin(oidc_settings: Settings):
    store = AuthStore(oidc_settings)
    store.create_or_link_oidc_user(
        oidc_sub="oidc-sub-1",
        username="trader",
        first_name="Pat",
        last_name="Lee",
        email="pat@example.com",
    )
    record = store.create_or_link_oidc_user(
        oidc_sub="oidc-sub-1",
        username="ignored",
        first_name="Jordan",
        last_name="Kim",
        email="jordan@example.com",
    )
    assert record.username == "trader"
    assert record.first_name == "Jordan"
    assert record.last_name == "Kim"
    assert record.email == "jordan@example.com"


def test_update_profile_rejected_in_oidc_mode(oidc_settings: Settings):
    store = AuthStore(oidc_settings)
    store.create_or_link_oidc_user(
        oidc_sub="oidc-sub-1",
        username="trader",
        first_name="Pat",
    )
    client = TestClient(app)
    token = SessionManager(oidc_settings).create_token("trader", oidc_sub="oidc-sub-1")
    response = client.put(
        "/api/auth/account/profile",
        json={"first_name": "New"},
        cookies={"brokerai_session": token},
    )
    assert response.status_code == 409


def test_me_includes_oidc_identity_fields(oidc_settings: Settings):
    store = AuthStore(oidc_settings)
    store.create_or_link_oidc_user(
        oidc_sub="oidc-sub-1",
        username="trader",
        first_name="Pat",
        last_name="Lee",
        email="pat@example.com",
    )
    client = TestClient(app)
    token = SessionManager(oidc_settings).create_token("trader", oidc_sub="oidc-sub-1")
    response = client.get("/api/auth/me", cookies={"brokerai_session": token})
    assert response.status_code == 200
    payload = response.json()
    assert payload["auth_mode"] == "oidc"
    assert payload["identity_managed_by_idp"] is True
    assert payload["email"] == "pat@example.com"
    assert payload["first_name"] == "Pat"
    assert payload["display_name"] == "Pat"
    assert payload["last_name"] == "Lee"


def test_legacy_builtin_session_rejected_in_oidc_mode(oidc_settings: Settings):
    store = AuthStore(oidc_settings)
    store.create_or_link_oidc_user(
        oidc_sub="oidc-sub-1",
        username="trader",
    )
    client = TestClient(app)
    legacy_token = SessionManager(oidc_settings).create_token("trader")
    response = client.get("/api/auth/me", cookies={"brokerai_session": legacy_token})
    assert response.status_code == 401


def test_allowed_sub_rejects_unauthorized_subject(oidc_settings: Settings, monkeypatch):
    monkeypatch.setenv("BROKERAI_OIDC_ALLOWED_SUB", "allowed-only")
    reload_settings()
    store = AuthStore(get_settings())
    with pytest.raises(ValueError, match="not allowed"):
        store.create_or_link_oidc_user(
            oidc_sub="other-subject",
            username="trader",
        )


def test_secure_cookie_when_forwarded_proto_https(auth_client: TestClient):
    store = AuthStore()
    store.create_user("admin", hash_password("BrokerAI!2026Password"))
    response = auth_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "BrokerAI!2026Password"},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert response.status_code == 200
    cookie = response.headers.get("set-cookie", "")
    assert "Secure" in cookie


@pytest.mark.asyncio
async def test_oidc_callback_sets_session_cookie(oidc_settings: Settings, tmp_path, monkeypatch):
    from brokerai.auth.oidc_client import OidcClient

    monkeypatch.setenv("BROKERAI_DATA_DIR", str(oidc_settings.data_dir))
    reload_settings()

    client = TestClient(app)
    oidc = OidcClient(get_settings())
    metadata = AsyncMock()
    metadata.token_endpoint = "https://auth.example.com/token"
    metadata.jwks_uri = "https://auth.example.com/jwks"
    metadata.end_session_endpoint = None

    signed_state = oidc._state_serializer.dumps(
        {
            "state": "state-1",
            "code_verifier": "verifier",
            "redirect_uri": "http://testserver/api/auth/oidc/callback",
        }
    )

    with (
        patch.object(OidcClient, "metadata", AsyncMock(return_value=metadata)),
        patch(
            "brokerai.auth.oidc_client.AsyncOAuth2Client.fetch_token",
            AsyncMock(return_value={"id_token": "fake-token"}),
        ),
        patch.object(
            OidcClient,
            "_verify_id_token",
            AsyncMock(
                return_value={
                    "sub": "oidc-sub-1",
                    "preferred_username": "trader",
                    "given_name": "Pat",
                }
            ),
        ),
    ):
        response = client.get(
            "/api/auth/oidc/callback?code=abc&state=state-1",
            cookies={"brokerai_oidc_state": signed_state},
            follow_redirects=False,
        )

    assert response.status_code == 302
    # New admins are seeded into the post-admin onboarding wizard.
    assert response.headers["location"] == "/setup"
    assert "brokerai_session=" in response.headers.get("set-cookie", "")
    saved = json.loads((oidc_settings.auth_dir / "users.json").read_text())
    assert saved["oidc_sub"] == "oidc-sub-1"


def test_validate_startup_settings_requires_oidc_env(tmp_path, monkeypatch):
    from brokerai.config.settings import validate_startup_settings

    monkeypatch.setenv("BROKERAI_AUTH_MODE", "oidc")
    reload_settings()
    with pytest.raises(RuntimeError, match="OIDC auth mode requires"):
        validate_startup_settings(get_settings())
