"""Tests for optional TOTP MFA pending tokens and login gate helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from brokerai.auth.mfa_pending import MfaPendingManager
from brokerai.auth.supabase_auth import normalize_totp_qr_code, verified_totp_factors


def test_normalize_totp_qr_code_wraps_raw_svg():
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'
    normalized = normalize_totp_qr_code(svg)
    assert normalized.startswith("data:image/svg+xml;charset=utf-8,")
    assert "<svg" not in normalized
    from urllib.parse import unquote

    assert unquote(normalized.split(",", 1)[1]) == svg


def test_normalize_totp_qr_code_keeps_data_uri():
    data_uri = "data:image/png;base64,abc123"
    assert normalize_totp_qr_code(data_uri) == data_uri


def test_verified_totp_factors_filters_status_and_type():
    factors = [
        {"id": "a", "status": "verified", "factor_type": "totp"},
        {"id": "b", "status": "unverified", "factor_type": "totp"},
        {"id": "c", "status": "verified", "factor_type": "phone"},
        {"id": "d", "status": "verified", "type": "totp"},
    ]
    assert [f["id"] for f in verified_totp_factors(factors)] == ["a", "d"]


def test_mfa_pending_roundtrip(monkeypatch):
    monkeypatch.setenv("BROKERAI_SECRET_KEY", "test-secret-for-mfa")
    from brokerai.config.settings import reload_settings

    reload_settings()
    mgr = MfaPendingManager()
    token = mgr.create(
        username="admin",
        access_token="access-jwt",
        purpose="login",
        factor_id="factor-1",
        oidc_sub="user-1",
    )
    pending = mgr.verify(token, purpose="login")
    assert pending is not None
    assert pending["username"] == "admin"
    assert pending["access_token"] == "access-jwt"
    assert pending["factor_id"] == "factor-1"
    assert pending["oidc_sub"] == "user-1"
    assert mgr.verify(token, purpose="enroll") is None


def test_mfa_pending_rejects_tampered_token(monkeypatch):
    monkeypatch.setenv("BROKERAI_SECRET_KEY", "test-secret-for-mfa")
    from brokerai.config.settings import reload_settings

    reload_settings()
    mgr = MfaPendingManager()
    token = mgr.create(
        username="admin",
        access_token="access-jwt",
        purpose="enroll",
        factor_id="factor-1",
    )
    assert mgr.verify(token + "x", purpose="enroll") is None


@pytest.mark.asyncio
async def test_login_returns_mfa_required_when_totp_enrolled(monkeypatch, tmp_path):
    monkeypatch.setenv("BROKERAI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BROKERAI_SECRET_KEY", "test-secret-for-mfa")
    monkeypatch.setenv("BROKERAI_AUTH_MODE", "builtin")
    monkeypatch.setenv("BROKERAI_SUPABASE_URL", "http://supabase.test")
    monkeypatch.setenv("BROKERAI_SUPABASE_SERVICE_ROLE_KEY", "service-role")
    from brokerai.config.settings import reload_settings

    reload_settings()

    from brokerai.auth.password import hash_password
    from brokerai.auth.store import AuthStore
    from brokerai.web.routes import auth as auth_routes

    AuthStore().create_user(
        "admin",
        hash_password("BrokerAI!2026Password"),
        None,
        auth_sub="user-1",
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
    )

    access = "access-token"
    claims = {"sub": "user-1", "aal": "aal1"}

    with (
        patch(
            "brokerai.auth.supabase_auth.password_sign_in",
            new=AsyncMock(return_value={"access_token": access}),
        ),
        patch("brokerai.auth.supabase_auth.verify_access_token", return_value=claims),
        patch(
            "brokerai.auth.supabase_auth.admin_list_factors",
            new=AsyncMock(
                return_value=[{"id": "factor-1", "status": "verified", "factor_type": "totp"}]
            ),
        ),
        patch("brokerai.auth.supabase_auth.supabase_configured", return_value=True),
    ):
        request = MagicMock()
        request.cookies = {}
        request.headers = {}
        response = MagicMock()
        body = auth_routes.LoginRequest(
            username="admin@example.com",
            password="BrokerAI!2026Password",
        )
        result = await auth_routes.login(body, request, response)

    assert result["status"] == "mfa_required"
    assert result["mfa_token"]
    response.set_cookie.assert_not_called()


@pytest.mark.asyncio
async def test_local_hash_blocked_when_mfa_enrolled(monkeypatch, tmp_path):
    monkeypatch.setenv("BROKERAI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BROKERAI_SECRET_KEY", "test-secret-for-mfa")
    monkeypatch.setenv("BROKERAI_AUTH_MODE", "builtin")
    monkeypatch.setenv("BROKERAI_SUPABASE_URL", "http://supabase.test")
    monkeypatch.setenv("BROKERAI_SUPABASE_SERVICE_ROLE_KEY", "service-role")
    from brokerai.config.settings import reload_settings

    reload_settings()

    from brokerai.auth.password import hash_password
    from brokerai.auth.store import AuthStore
    from brokerai.auth.supabase_auth import SupabaseAuthError
    from brokerai.web.routes import auth as auth_routes

    AuthStore().create_user(
        "admin",
        hash_password("BrokerAI!2026Password"),
        None,
        auth_sub="user-1",
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
    )

    with (
        patch(
            "brokerai.auth.supabase_auth.password_sign_in",
            new=AsyncMock(side_effect=SupabaseAuthError("down", status_code=503)),
        ),
        patch("brokerai.auth.supabase_auth.supabase_configured", return_value=True),
        patch(
            "brokerai.auth.supabase_auth.user_has_verified_totp",
            new=AsyncMock(return_value=True),
        ),
    ):
        request = MagicMock()
        request.cookies = {}
        request.headers = {}
        response = MagicMock()
        body = auth_routes.LoginRequest(
            username="admin@example.com",
            password="BrokerAI!2026Password",
        )
        with pytest.raises(HTTPException) as exc:
            await auth_routes.login(body, request, response)
        assert exc.value.status_code == 401
