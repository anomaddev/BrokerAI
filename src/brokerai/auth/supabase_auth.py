"""Supabase Auth Admin / password helpers for self-hosted GoTrue."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx
import jwt

from brokerai.config.settings import get_settings

logger = logging.getLogger(__name__)


def normalize_totp_qr_code(qr_code: str) -> str:
    """Return a browser-safe image URL for GoTrue's TOTP ``qr_code`` field.

    GoTrue often returns a raw ``<svg>…</svg>`` string. Using that as an
    ``<img src>`` makes the browser request it as a relative URL (and can
    trigger HTTP 431). Convert raw SVG / bare base64 into a data URI.
    """
    value = (qr_code or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered.startswith(("data:", "http://", "https://", "blob:")):
        return value
    if value.lstrip().startswith("<svg") or value.lstrip().startswith("<?xml"):
        return f"data:image/svg+xml;charset=utf-8,{quote(value, safe='')}"
    # Bare base64 PNG from some Auth versions.
    return f"data:image/png;base64,{value}"


class SupabaseAuthError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def supabase_configured() -> bool:
    settings = get_settings()
    return bool(
        str(settings.supabase_url or "").strip()
        and str(settings.supabase_service_role_key or "").strip()
    )


def _base_url() -> str:
    return get_settings().supabase_url.rstrip("/")


def _service_headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


def _anon_headers() -> dict[str, str]:
    settings = get_settings()
    key = settings.supabase_anon_key or settings.supabase_service_role_key
    return {
        "apikey": key,
        "Content-Type": "application/json",
    }


def build_profile_user_metadata(
    *,
    username: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> dict[str, Any]:
    """BrokerAI profile fields mirrored into Supabase Auth ``user_metadata``.

    Display name (``full_name`` / ``name``) is the first name — matching BrokerAI
    header/menu labeling. First and last are stored separately.
    """
    metadata: dict[str, Any] = {"username": username}
    if first_name:
        metadata["first_name"] = first_name
        metadata["full_name"] = first_name
        metadata["name"] = first_name
    if last_name:
        metadata["last_name"] = last_name
    return metadata


async def admin_create_user(
    *,
    email: str,
    password: str,
    username: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> dict[str, Any]:
    """Create a user via Auth Admin API (service role)."""
    payload = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": build_profile_user_metadata(
            username=username,
            first_name=first_name,
            last_name=last_name,
        ),
        "app_metadata": {"username": username, "role": "admin"},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_base_url()}/auth/v1/admin/users",
            headers=_service_headers(),
            json=payload,
        )
    if response.status_code >= 400:
        detail = response.text
        raise SupabaseAuthError(
            f"Supabase admin create user failed: {detail}",
            status_code=response.status_code,
        )
    return response.json()


async def admin_update_user_profile(
    *,
    user_id: str,
    username: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> dict[str, Any]:
    """Replace Auth profile metadata so Studio matches BrokerAI / setup."""
    payload = {
        "user_metadata": build_profile_user_metadata(
            username=username,
            first_name=first_name,
            last_name=last_name,
        ),
        "app_metadata": {"username": username, "role": "admin"},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.put(
            f"{_base_url()}/auth/v1/admin/users/{user_id}",
            headers=_service_headers(),
            json=payload,
        )
    if response.status_code >= 400:
        raise SupabaseAuthError(
            f"Supabase admin update user failed: {response.text}",
            status_code=response.status_code,
        )
    return response.json()


async def password_sign_in(*, email: str, password: str) -> dict[str, Any]:
    """Sign in with email/password; returns session payload including access_token."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_base_url()}/auth/v1/token?grant_type=password",
            headers=_anon_headers(),
            json={"email": email, "password": password},
        )
    if response.status_code >= 400:
        raise SupabaseAuthError(
            "Invalid email or password",
            status_code=response.status_code,
        )
    return response.json()


async def admin_update_password(*, user_id: str, password: str) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.put(
            f"{_base_url()}/auth/v1/admin/users/{user_id}",
            headers=_service_headers(),
            json={"password": password},
        )
    if response.status_code >= 400:
        raise SupabaseAuthError(
            f"Failed to update password: {response.text}",
            status_code=response.status_code,
        )


def verify_access_token(token: str) -> dict[str, Any]:
    """Verify a Supabase JWT with the shared JWT secret (HS256 self-host default)."""
    settings = get_settings()
    secret = (settings.supabase_jwt_secret or "").strip()
    if not secret:
        raise SupabaseAuthError("BROKERAI_SUPABASE_JWT_SECRET is not configured")
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise SupabaseAuthError(f"Invalid access token: {exc}") from exc


def email_for_username(username: str) -> str:
    """Deterministic local email for single-tenant builtin → Supabase mapping."""
    return f"{username}@users.brokerai.local"


def _user_headers(access_token: str) -> dict[str, str]:
    settings = get_settings()
    key = settings.supabase_anon_key or settings.supabase_service_role_key
    return {
        "apikey": key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _raise_for_status(response: httpx.Response, *, fallback: str) -> None:
    if response.status_code < 400:
        return
    detail = (response.text or "").strip() or fallback
    raise SupabaseAuthError(detail, status_code=response.status_code)


async def admin_list_factors(user_id: str) -> list[dict[str, Any]]:
    """List MFA factors for a user via Auth Admin API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{_base_url()}/auth/v1/admin/users/{user_id}/factors",
            headers=_service_headers(),
        )
    if response.status_code == 404:
        return []
    _raise_for_status(response, fallback="Failed to list MFA factors")
    payload = response.json()
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    factors = payload.get("factors") if isinstance(payload, dict) else None
    if isinstance(factors, list):
        return [item for item in factors if isinstance(item, dict)]
    return []


def verified_totp_factors(factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        factor
        for factor in factors
        if str(factor.get("status") or "").lower() == "verified"
        and str(factor.get("factor_type") or factor.get("type") or "").lower() == "totp"
    ]


async def user_has_verified_totp(user_id: str) -> bool:
    factors = await admin_list_factors(user_id)
    return bool(verified_totp_factors(factors))


async def mfa_enroll_totp(
    *,
    access_token: str,
    friendly_name: str = "Authenticator",
    issuer: str = "BrokerAI",
) -> dict[str, Any]:
    """Start TOTP enrollment; returns factor id + QR/secret payload."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_base_url()}/auth/v1/factors",
            headers=_user_headers(access_token),
            json={
                "factor_type": "totp",
                "friendly_name": friendly_name,
                "issuer": issuer,
            },
        )
    _raise_for_status(response, fallback="Failed to enroll authenticator")
    return response.json()


async def mfa_challenge(*, access_token: str, factor_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_base_url()}/auth/v1/factors/{factor_id}/challenge",
            headers=_user_headers(access_token),
            json={},
        )
    _raise_for_status(response, fallback="Failed to create MFA challenge")
    return response.json()


async def mfa_verify(
    *,
    access_token: str,
    factor_id: str,
    challenge_id: str,
    code: str,
) -> dict[str, Any]:
    """Verify a TOTP code; returns a new session with aal2 on success."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_base_url()}/auth/v1/factors/{factor_id}/verify",
            headers=_user_headers(access_token),
            json={"challenge_id": challenge_id, "code": code},
        )
    _raise_for_status(response, fallback="Invalid authenticator code")
    return response.json()


async def mfa_unenroll(*, access_token: str, factor_id: str) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.delete(
            f"{_base_url()}/auth/v1/factors/{factor_id}",
            headers=_user_headers(access_token),
        )
    _raise_for_status(response, fallback="Failed to remove authenticator")


async def admin_delete_factor(*, user_id: str, factor_id: str) -> None:
    """Remove a factor via Admin API (cleanup of abandoned enrollments)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.delete(
            f"{_base_url()}/auth/v1/admin/users/{user_id}/factors/{factor_id}",
            headers=_service_headers(),
        )
    if response.status_code in (404, 405):
        return
    _raise_for_status(response, fallback="Failed to delete MFA factor")


async def mfa_challenge_and_verify(
    *,
    access_token: str,
    factor_id: str,
    code: str,
) -> dict[str, Any]:
    challenge = await mfa_challenge(access_token=access_token, factor_id=factor_id)
    challenge_id = str(challenge.get("id") or "")
    if not challenge_id:
        raise SupabaseAuthError("MFA challenge did not return an id", status_code=502)
    return await mfa_verify(
        access_token=access_token,
        factor_id=factor_id,
        challenge_id=challenge_id,
        code=code,
    )
