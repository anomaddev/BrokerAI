from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from brokerai.config_backup.change_labels import (
    describe_general_settings_change,
    describe_market_indicators_change,
)
from brokerai.config_backup.hooks import auto_backup_before
from brokerai.auth import (
    AuthStore,
    PasswordValidationError,
    SessionManager,
    UserRecord,
    hash_password,
    is_valid_email,
    is_valid_username,
    normalize_optional_name,
    username_from_email,
    validate_password,
    verify_password,
)
from brokerai.auth.cookies import delete_session_cookie, set_session_cookie
from brokerai.auth.general_settings import normalize_general_settings
from brokerai.auth.mode import auth_mode, is_builtin_mode, is_oidc_mode
from brokerai.auth.oidc_client import OidcClient
from brokerai.auth.profile_photo import (
    delete_profile_photo as remove_stored_profile_photo,
    is_remote_photo_url,
    resolve_profile_photo_path,
    resolve_profile_photo_url,
    save_profile_photo,
)
from brokerai.config.settings import get_settings
from brokerai.market_sessions import TRADING_SESSIONS, normalize_market_indicators, session_definition_payload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginMfaRequest(BaseModel):
    mfa_token: str
    code: str


class MfaPasswordRequest(BaseModel):
    password: str


class MfaVerifyEnrollRequest(BaseModel):
    enroll_token: str
    code: str


class MfaDisableRequest(BaseModel):
    password: str
    factor_id: str


class ChangeUsernameRequest(BaseModel):
    username: str
    current_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    password: str
    confirm_password: str


class UpdateProfileRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None


class UpdateDisplaySettingsRequest(BaseModel):
    market_indicators: dict[str, bool]


class UpdateGeneralSettingsRequest(BaseModel):
    timezone_auto: bool
    timezone: str | None = None
    show_utc_times: bool
    time_format: Literal["12h", "24h"] = "24h"


def _reject_when_oidc_enabled() -> None:
    if is_oidc_mode():
        raise HTTPException(
            status_code=409,
            detail="Built-in password authentication is disabled while OIDC auth is enabled",
        )


async def _sync_supabase_profile(user: UserRecord) -> None:
    """Keep Supabase Auth user_metadata aligned with BrokerAI profile fields."""
    from brokerai.auth.supabase_auth import (
        SupabaseAuthError,
        admin_update_user_profile,
        supabase_configured,
    )

    if not supabase_configured() or not user.oidc_sub:
        return
    try:
        await admin_update_user_profile(
            user_id=user.oidc_sub,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
    except SupabaseAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code or 502,
            detail=str(exc),
        ) from exc


def get_current_username(request: Request) -> str | None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    verified = SessionManager().verify_token(token)
    if verified is None:
        return None
    username, token_oidc_sub = verified
    store = AuthStore()
    user = store.get_user()
    if user is None or user.username != username:
        return None
    if is_oidc_mode():
        if user.oidc_sub is None:
            return None
        if not token_oidc_sub or token_oidc_sub != user.oidc_sub:
            return None
    return username


async def require_auth(request: Request) -> str:
    username = get_current_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return username


def _mfa_available() -> bool:
    from brokerai.auth.supabase_auth import supabase_configured

    return is_builtin_mode() and supabase_configured()


@router.get("/config")
async def auth_config() -> dict[str, str | bool]:
    from brokerai.auth.supabase_auth import supabase_configured
    from brokerai.config.settings import get_settings

    store = AuthStore()
    settings = get_settings()
    payload: dict[str, str | bool] = {
        "mode": auth_mode(),
        "setup_complete": store.is_setup_complete(),
        "mfa_available": _mfa_available(),
        "supabase_configured": supabase_configured(),
    }
    # Publishable values only — never expose the service_role key.
    if supabase_configured() and settings.supabase_anon_key:
        payload["supabase_url"] = settings.supabase_url.rstrip("/")
        payload["supabase_anon_key"] = settings.supabase_anon_key
    return payload


@router.get("/setup/status")
async def setup_status() -> dict[str, bool]:
    return {"setup_complete": AuthStore().is_setup_complete()}


@router.post("/setup")
async def setup(
    request: Request,
    response: Response,
    password: str = Form(...),
    confirm_password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(""),
    email: str = Form(...),
    username: str | None = Form(None),
    profile_photo: UploadFile | None = File(None),
) -> dict[str, str | bool | None]:
    _reject_when_oidc_enabled()
    store = AuthStore()
    if store.is_setup_complete():
        raise HTTPException(status_code=409, detail="Setup already complete")

    email_normalized = email.strip().lower()
    if not is_valid_email(email_normalized):
        raise HTTPException(status_code=400, detail="Invalid email address")

    try:
        resolved_first = normalize_optional_name(first_name)
        resolved_last = normalize_optional_name(last_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not resolved_first:
        raise HTTPException(status_code=400, detail="First name is required")

    resolved_username = (username or "").strip().lower() or username_from_email(email_normalized)
    if not is_valid_username(resolved_username):
        raise HTTPException(status_code=400, detail="Invalid username derived from email")

    try:
        validate_password(password, confirm_password)
    except PasswordValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    photo_data: bytes | None = None
    if profile_photo and profile_photo.filename:
        try:
            raw = await profile_photo.read()
            if raw:
                photo_data = raw
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Failed to read profile photo") from exc

    from brokerai.auth.supabase_auth import (
        SupabaseAuthError,
        admin_create_user,
        email_for_username,
        supabase_configured,
    )

    auth_sub: str | None = None
    auth_email = email_normalized
    password_hash = hash_password(password)
    if supabase_configured():
        # Prefer the admin's real email; fall back to deterministic local mapping.
        auth_email = email_normalized or email_for_username(resolved_username)
        try:
            created = await admin_create_user(
                email=auth_email,
                password=password,
                username=resolved_username,
                first_name=resolved_first,
                last_name=resolved_last,
            )
            auth_sub = str(created.get("id") or "") or None
            # Password lives in Supabase Auth; keep local hash for offline fallback.
        except SupabaseAuthError as exc:
            raise HTTPException(
                status_code=exc.status_code or 502,
                detail=str(exc),
            ) from exc

    profile_photo_ref: str | None = None
    if photo_data:
        try:
            store.ensure_dir()
            profile_id = auth_sub or f"local:{resolved_username}"
            profile_photo_ref = await save_profile_photo(
                store.auth_dir,
                photo_data,
                profile_id=profile_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = store.create_user(
        resolved_username,
        password_hash,
        profile_photo_ref,
        auth_sub=auth_sub,
        email=auth_email,
        first_name=resolved_first,
        last_name=resolved_last,
    )
    await _provision_ssh_user(resolved_username, password)

    token = SessionManager().create_token(
        record.username, oidc_sub=record.oidc_sub if record.oidc_sub else None
    )
    set_session_cookie(response, token, request)
    photo_url = resolve_profile_photo_url(stored=record.profile_photo, auth_dir=store.auth_dir)
    return {
        "username": record.username,
        "status": "created",
        "has_profile_photo": bool(photo_url),
        "profile_photo_url": photo_url,
    }


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response) -> dict[str, str]:
    _reject_when_oidc_enabled()
    store = AuthStore()
    if not store.is_setup_complete():
        raise HTTPException(status_code=400, detail="Setup required")
    user = store.get_user()
    identifier = body.username.strip()
    identifier_l = identifier.lower()
    if user is None or (
        user.username != identifier
        and user.username != identifier_l
        and (user.email or "").lower() != identifier_l
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    from brokerai.auth.mfa_pending import MfaPendingManager
    from brokerai.auth.supabase_auth import (
        SupabaseAuthError,
        email_for_username,
        password_sign_in,
        supabase_configured,
        user_has_verified_totp,
        verified_totp_factors,
        admin_list_factors,
        verify_access_token,
    )

    authenticated = False
    access = ""
    claims: dict[str, Any] | None = None
    if supabase_configured() and (user.email or user.oidc_sub):
        try:
            session = await password_sign_in(
                email=user.email or email_for_username(user.username),
                password=body.password,
            )
            access = str(session.get("access_token") or "")
            if access:
                claims = verify_access_token(access)
                sub = str(claims.get("sub") or "")
                if user.oidc_sub and sub and sub != user.oidc_sub:
                    raise HTTPException(status_code=401, detail="Invalid credentials")
                authenticated = True
        except SupabaseAuthError:
            authenticated = False

    if not authenticated:
        # Never bypass MFA via local hash when the Auth user has a verified factor.
        if supabase_configured() and user.oidc_sub:
            try:
                if await user_has_verified_totp(user.oidc_sub):
                    raise HTTPException(status_code=401, detail="Invalid credentials")
            except SupabaseAuthError:
                raise HTTPException(status_code=401, detail="Invalid credentials") from None
        if not user.password_hash or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    elif access and claims is not None:
        aal = str(claims.get("aal") or "aal1")
        sub = str(claims.get("sub") or user.oidc_sub or "")
        if aal != "aal2" and sub:
            try:
                factors = await admin_list_factors(sub)
            except SupabaseAuthError as exc:
                raise HTTPException(
                    status_code=exc.status_code or 502,
                    detail=str(exc),
                ) from exc
            totp = verified_totp_factors(factors)
            if totp:
                factor_id = str(totp[0].get("id") or "")
                if not factor_id:
                    raise HTTPException(status_code=502, detail="MFA factor is misconfigured")
                mfa_token = MfaPendingManager().create(
                    username=user.username,
                    access_token=access,
                    purpose="login",
                    factor_id=factor_id,
                    oidc_sub=user.oidc_sub,
                )
                return {
                    "username": user.username,
                    "status": "mfa_required",
                    "mfa_token": mfa_token,
                }

    token = SessionManager().create_token(
        user.username, oidc_sub=user.oidc_sub if user.oidc_sub else None
    )
    set_session_cookie(response, token, request)
    return {"username": user.username, "status": "ok"}


@router.post("/login/mfa")
async def login_mfa(
    body: LoginMfaRequest, request: Request, response: Response
) -> dict[str, str]:
    """Complete builtin login after password step when TOTP is enrolled."""
    _reject_when_oidc_enabled()
    from brokerai.auth.mfa_pending import MfaPendingManager
    from brokerai.auth.supabase_auth import SupabaseAuthError, mfa_challenge_and_verify

    pending = MfaPendingManager().verify(body.mfa_token.strip(), purpose="login")
    if pending is None:
        raise HTTPException(status_code=401, detail="MFA session expired — sign in again")
    factor_id = pending.get("factor_id")
    if not factor_id:
        raise HTTPException(status_code=400, detail="MFA session is missing a factor")

    store = AuthStore()
    user = store.get_user()
    if user is None or user.username != pending["username"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    code = "".join(ch for ch in body.code.strip() if ch.isdigit())
    if len(code) < 6:
        raise HTTPException(status_code=400, detail="Enter the 6-digit authenticator code")

    try:
        await mfa_challenge_and_verify(
            access_token=pending["access_token"],
            factor_id=factor_id,
            code=code,
        )
    except SupabaseAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code or 401,
            detail="Invalid authenticator code",
        ) from exc

    token = SessionManager().create_token(
        user.username, oidc_sub=user.oidc_sub if user.oidc_sub else None
    )
    set_session_cookie(response, token, request)
    return {"username": user.username, "status": "ok"}


@router.get("/mfa/status")
async def mfa_status(_username: str = Depends(require_auth)) -> dict[str, object]:
    """Return whether optional TOTP MFA is available / enrolled for the admin."""
    if not _mfa_available():
        return {"available": False, "enabled": False, "factors": []}

    store = AuthStore()
    user = store.get_user()
    if user is None or not user.oidc_sub:
        return {"available": True, "enabled": False, "factors": []}

    from brokerai.auth.supabase_auth import (
        SupabaseAuthError,
        admin_list_factors,
        verified_totp_factors,
    )

    try:
        factors = await admin_list_factors(user.oidc_sub)
    except SupabaseAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code or 502,
            detail=str(exc),
        ) from exc

    totp = verified_totp_factors(factors)
    return {
        "available": True,
        "enabled": bool(totp),
        "factors": [
            {
                "id": str(factor.get("id") or ""),
                "friendly_name": factor.get("friendly_name") or "Authenticator",
                "factor_type": "totp",
                "status": "verified",
            }
            for factor in totp
            if factor.get("id")
        ],
    }


@router.post("/mfa/enroll")
async def mfa_enroll(
    body: MfaPasswordRequest,
    _username: str = Depends(require_auth),
) -> dict[str, str]:
    """Begin optional TOTP enrollment (requires current password)."""
    _reject_when_oidc_enabled()
    if not _mfa_available():
        raise HTTPException(status_code=409, detail="Authenticator 2FA is not available")

    from brokerai.auth.mfa_pending import MfaPendingManager
    from brokerai.auth.supabase_auth import (
        SupabaseAuthError,
        admin_delete_factor,
        admin_list_factors,
        email_for_username,
        mfa_enroll_totp,
        normalize_totp_qr_code,
        password_sign_in,
        verified_totp_factors,
        verify_access_token,
    )

    store = AuthStore()
    user = store.get_user()
    if user is None or not user.oidc_sub:
        raise HTTPException(status_code=409, detail="Authenticator 2FA requires Supabase Auth")

    try:
        existing = await admin_list_factors(user.oidc_sub)
    except SupabaseAuthError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
    if verified_totp_factors(existing):
        raise HTTPException(status_code=409, detail="Authenticator 2FA is already enabled")

    # Drop abandoned unverified enrollments so a fresh QR can be issued.
    for factor in existing:
        status = str(factor.get("status") or "").lower()
        factor_id = str(factor.get("id") or "")
        if status == "unverified" and factor_id:
            await admin_delete_factor(user_id=user.oidc_sub, factor_id=factor_id)

    try:
        session = await password_sign_in(
            email=user.email or email_for_username(user.username),
            password=body.password,
        )
        access = str(session.get("access_token") or "")
        if not access:
            raise SupabaseAuthError("Sign-in did not return an access token", status_code=502)
        claims = verify_access_token(access)
        sub = str(claims.get("sub") or "")
        if sub and sub != user.oidc_sub:
            raise HTTPException(status_code=401, detail="Incorrect password")
        enrolled = await mfa_enroll_totp(access_token=access)
    except SupabaseAuthError as exc:
        if exc.status_code in (400, 401):
            raise HTTPException(status_code=401, detail="Incorrect password") from exc
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc

    factor_id = str(enrolled.get("id") or "")
    totp = enrolled.get("totp") if isinstance(enrolled.get("totp"), dict) else {}
    qr_code = normalize_totp_qr_code(str(totp.get("qr_code") or ""))
    secret = str(totp.get("secret") or "")
    uri = str(totp.get("uri") or "")
    if not factor_id or not (qr_code or secret):
        raise HTTPException(status_code=502, detail="Authenticator enrollment failed")

    enroll_token = MfaPendingManager().create(
        username=user.username,
        access_token=access,
        purpose="enroll",
        factor_id=factor_id,
        oidc_sub=user.oidc_sub,
    )
    return {
        "status": "pending",
        "enroll_token": enroll_token,
        "factor_id": factor_id,
        "qr_code": qr_code,
        "secret": secret,
        "uri": uri,
    }


@router.post("/mfa/verify")
async def mfa_verify_enroll(
    body: MfaVerifyEnrollRequest,
    _username: str = Depends(require_auth),
) -> dict[str, str | bool]:
    """Confirm TOTP enrollment with the first authenticator code."""
    _reject_when_oidc_enabled()
    from brokerai.auth.mfa_pending import MfaPendingManager
    from brokerai.auth.supabase_auth import SupabaseAuthError, mfa_challenge_and_verify

    pending = MfaPendingManager().verify(body.enroll_token.strip(), purpose="enroll")
    if pending is None:
        raise HTTPException(status_code=401, detail="Enrollment expired — start again")
    factor_id = pending.get("factor_id")
    if not factor_id:
        raise HTTPException(status_code=400, detail="Enrollment is missing a factor")

    store = AuthStore()
    user = store.get_user()
    if user is None or user.username != pending["username"]:
        raise HTTPException(status_code=401, detail="Not authenticated")

    code = "".join(ch for ch in body.code.strip() if ch.isdigit())
    if len(code) < 6:
        raise HTTPException(status_code=400, detail="Enter the 6-digit authenticator code")

    try:
        await mfa_challenge_and_verify(
            access_token=pending["access_token"],
            factor_id=factor_id,
            code=code,
        )
    except SupabaseAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code or 401,
            detail="Invalid authenticator code",
        ) from exc

    return {"status": "enabled", "enabled": True, "factor_id": factor_id}


@router.post("/mfa/disable")
async def mfa_disable(
    body: MfaDisableRequest,
    _username: str = Depends(require_auth),
) -> dict[str, str | bool]:
    """Remove a verified TOTP factor (requires current password).

    Uses the Auth Admin API after password verification so disable works even
    when the password grant only yields ``aal1`` (user unenroll often needs
    ``aal2``).
    """
    _reject_when_oidc_enabled()
    if not _mfa_available():
        raise HTTPException(status_code=409, detail="Authenticator 2FA is not available")

    from brokerai.auth.supabase_auth import (
        SupabaseAuthError,
        admin_delete_factor,
        admin_list_factors,
        email_for_username,
        password_sign_in,
        verified_totp_factors,
        verify_access_token,
    )

    store = AuthStore()
    user = store.get_user()
    if user is None or not user.oidc_sub:
        raise HTTPException(status_code=409, detail="Authenticator 2FA requires Supabase Auth")

    factor_id = body.factor_id.strip()
    if not factor_id:
        raise HTTPException(status_code=400, detail="factor_id is required")

    try:
        session = await password_sign_in(
            email=user.email or email_for_username(user.username),
            password=body.password,
        )
        access = str(session.get("access_token") or "")
        if not access:
            raise SupabaseAuthError("Sign-in did not return an access token", status_code=502)
        claims = verify_access_token(access)
        sub = str(claims.get("sub") or "")
        if sub and sub != user.oidc_sub:
            raise HTTPException(status_code=401, detail="Incorrect password")

        # When MFA is enrolled, password grant stays at aal1 — still proves the
        # password. Confirm the factor belongs to this user, then delete via admin.
        factors = await admin_list_factors(user.oidc_sub)
        if factor_id not in {str(f.get("id") or "") for f in verified_totp_factors(factors)}:
            raise HTTPException(status_code=404, detail="Authenticator not found")
        await admin_delete_factor(user_id=user.oidc_sub, factor_id=factor_id)
    except SupabaseAuthError as exc:
        if exc.status_code in (400, 401):
            raise HTTPException(status_code=401, detail="Incorrect password") from exc
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc

    return {"status": "disabled", "enabled": False}


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    delete_session_cookie(response)
    return {"status": "logged_out"}


@router.get("/oidc/login")
async def oidc_login(request: Request, response: Response) -> Response:
    if not is_oidc_mode():
        raise HTTPException(status_code=404, detail="OIDC auth is not enabled")
    try:
        redirect_url = await OidcClient().build_login_redirect(request, response)
    except Exception as exc:
        # Common when BROKERAI_AUTH_MODE=oidc but the IdP is unreachable.
        logger.warning("OIDC login redirect failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "Identity provider is unreachable. Check BROKERAI_OIDC_ISSUER "
                "or set BROKERAI_AUTH_MODE=builtin."
            ),
        ) from exc
    response.status_code = 302
    response.headers["Location"] = redirect_url
    return response


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> Response:
    if not is_oidc_mode():
        raise HTTPException(status_code=404, detail="OIDC auth is not enabled")
    await OidcClient().handle_callback(
        request,
        response,
        code=code,
        state=state,
        error=error,
        error_description=error_description,
    )
    from brokerai.auth.onboarding import resolve_onboarding_status
    from brokerai.auth.store import AuthStore

    onboarding = resolve_onboarding_status(auth_complete=AuthStore().is_setup_complete())
    response.status_code = 302
    response.headers["Location"] = (
        "/setup" if not onboarding.get("onboarding_complete") else "/"
    )
    return response


@router.post("/oidc/logout")
async def oidc_logout(request: Request, response: Response) -> dict[str, str | None]:
    if not is_oidc_mode():
        raise HTTPException(status_code=404, detail="OIDC auth is not enabled")
    logout_url = await OidcClient().logout(request, response)
    return {"status": "logged_out", "logout_url": logout_url}


@router.get("/me")
async def me(username: str = Depends(require_auth)) -> dict[str, str | bool | None]:
    store = AuthStore()
    user = store.get_user()
    photo_url = (
        resolve_profile_photo_url(stored=user.profile_photo, auth_dir=store.auth_dir)
        if user
        else None
    )
    mode = auth_mode()
    first_name = user.first_name if user else None
    last_name = user.last_name if user else None
    return {
        "username": username,
        "has_profile_photo": bool(photo_url),
        "profile_photo_url": photo_url,
        "display_name": first_name,
        "first_name": first_name,
        "last_name": last_name,
        "email": user.email if user else None,
        "auth_mode": mode,
        "identity_managed_by_idp": is_oidc_mode(),
    }


@router.get("/profile-photo", response_model=None)
async def get_profile_photo(
    _username: str = Depends(require_auth),
) -> FileResponse | RedirectResponse:
    store = AuthStore()
    user = store.get_user()
    if user is None or not user.profile_photo:
        raise HTTPException(status_code=404, detail="Profile photo not found")
    if is_remote_photo_url(user.profile_photo):
        return RedirectResponse(url=user.profile_photo, status_code=302)
    path = resolve_profile_photo_path(store.auth_dir, user.profile_photo)
    if path is None:
        raise HTTPException(status_code=404, detail="Profile photo not found")
    return FileResponse(path)


@router.put("/profile-photo")
async def upload_profile_photo(
    file: UploadFile = File(...),
    _username: str = Depends(require_auth),
) -> dict[str, str | bool | None]:
    store = AuthStore()
    user = store.get_user()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        photo_data = await file.read()
        stored = await save_profile_photo(
            store.auth_dir,
            photo_data,
            profile_id=store.profile_id() or store._profile_id_for(user),
            previous=user.profile_photo,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = store.set_profile_photo(stored)
    photo_url = resolve_profile_photo_url(stored=record.profile_photo, auth_dir=store.auth_dir)
    return {"status": "ok", "has_profile_photo": bool(photo_url), "profile_photo_url": photo_url}


@router.delete("/profile-photo")
async def delete_profile_photo(_username: str = Depends(require_auth)) -> dict[str, str | bool | None]:
    store = AuthStore()
    user = store.get_user()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    await remove_stored_profile_photo(store.auth_dir, stored=user.profile_photo)
    store.set_profile_photo(None)
    return {"status": "ok", "has_profile_photo": False, "profile_photo_url": None}


@router.put("/account/username")
async def change_username(
    body: ChangeUsernameRequest,
    request: Request,
    response: Response,
    username: str = Depends(require_auth),
) -> dict[str, str]:
    _reject_when_oidc_enabled()
    store = AuthStore()
    user = store.get_user()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")
    if not is_valid_username(body.username):
        raise HTTPException(status_code=400, detail="Invalid username")
    if body.username == user.username:
        return {"username": user.username, "status": "ok"}

    record = store.update_username(body.username)
    await _sync_supabase_profile(record)
    await _provision_ssh_user(record.username, body.current_password)

    token = SessionManager().create_token(
        record.username, oidc_sub=record.oidc_sub if record.oidc_sub else None
    )
    set_session_cookie(response, token, request)
    return {"username": record.username, "status": "ok"}


@router.put("/account/password")
async def change_password(
    body: ChangePasswordRequest,
    _username: str = Depends(require_auth),
) -> dict[str, str]:
    _reject_when_oidc_enabled()
    store = AuthStore()
    user = store.get_user()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")
    try:
        validate_password(body.password, body.confirm_password)
    except PasswordValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store.update_password(hash_password(body.password))
    from brokerai.auth.supabase_auth import (
        SupabaseAuthError,
        admin_update_password,
        supabase_configured,
    )

    if supabase_configured() and user.oidc_sub:
        try:
            await admin_update_password(user_id=user.oidc_sub, password=body.password)
        except SupabaseAuthError as exc:
            raise HTTPException(
                status_code=exc.status_code or 502,
                detail=str(exc),
            ) from exc
    await _update_ssh_password(user.username, body.password)
    return {"status": "ok"}


@router.put("/account/profile")
async def update_profile(
    body: UpdateProfileRequest,
    _username: str = Depends(require_auth),
) -> dict[str, str | None]:
    if is_oidc_mode():
        raise HTTPException(
            status_code=409,
            detail="Profile names are managed by your identity provider while OIDC auth is enabled",
        )
    store = AuthStore()
    if store.get_user() is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        first_name = normalize_optional_name(body.first_name)
        last_name = normalize_optional_name(body.last_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = store.update_profile(first_name, last_name)
    await _sync_supabase_profile(record)
    return {
        "status": "ok",
        "display_name": record.first_name,
        "first_name": record.first_name,
        "last_name": record.last_name,
    }


@router.get("/account/display")
async def get_display_settings(_username: str = Depends(require_auth)) -> dict[str, object]:
    store = AuthStore()
    user = store.get_user()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    indicators = user.resolved_market_indicators()
    return {
        "market_indicators": indicators,
        "markets": [session_definition_payload(session) for session in TRADING_SESSIONS],
    }


@router.put("/account/display")
async def update_display_settings(
    body: UpdateDisplaySettingsRequest,
    _username: str = Depends(require_auth),
) -> dict[str, object]:
    store = AuthStore()
    user = store.get_user()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    change_label = describe_market_indicators_change(
        user.resolved_market_indicators(),
        body.market_indicators,
    )
    await auto_backup_before(
        trigger="account.display",
        summary="Display settings",
        change_label=change_label or "Display settings",
    )
    try:
        record = store.update_market_indicators(body.market_indicators)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        "market_indicators": normalize_market_indicators(record.market_indicators),
    }


@router.get("/account/general")
async def get_general_settings(_username: str = Depends(require_auth)) -> dict[str, object]:
    store = AuthStore()
    user = store.get_user()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user.resolved_general_settings()


@router.put("/account/general")
async def update_general_settings(
    body: UpdateGeneralSettingsRequest,
    _username: str = Depends(require_auth),
) -> dict[str, object]:
    store = AuthStore()
    user = store.get_user()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    change_label = describe_general_settings_change(
        user.resolved_general_settings(),
        timezone_auto=body.timezone_auto,
        timezone=body.timezone,
        show_utc_times=body.show_utc_times,
        time_format=body.time_format,
    )
    await auto_backup_before(
        trigger="account.general",
        summary="General settings",
        change_label=change_label or "General settings",
    )
    try:
        record = store.update_general_settings(
            timezone_auto=body.timezone_auto,
            timezone=body.timezone,
            show_utc_times=body.show_utc_times,
            time_format=body.time_format,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    settings = record.resolved_general_settings()
    return {
        "status": "ok",
        **settings,
    }


async def _provision_ssh_user(username: str, password: str) -> None:
    if not is_builtin_mode():
        return
    script = Path("/opt/brokerai/scripts/provision-admin-user.sh")
    if not script.exists():
        script = Path(__file__).resolve().parents[3] / "scripts" / "provision-admin-user.sh"
    if not script.exists():
        logger.warning("SSH provisioning script not found — skipped")
        return

    def run() -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["sudo", "-n", str(script), username],
            input=password + "\n",
            text=True,
            capture_output=True,
            check=False,
        )
        return proc

    try:
        result = await asyncio.to_thread(run)
        if result.returncode != 0:
            logger.warning(
                "SSH provisioning failed (exit %s): %s",
                result.returncode,
                result.stderr.strip(),
            )
    except FileNotFoundError:
        logger.warning("sudo not available — SSH provisioning skipped")


async def _update_ssh_password(username: str, password: str) -> None:
    if not is_builtin_mode():
        return

    def run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sudo", "-n", "chpasswd"],
            input=f"{username}:{password}\n",
            text=True,
            capture_output=True,
            check=False,
        )

    try:
        result = await asyncio.to_thread(run)
        if result.returncode != 0:
            logger.warning(
                "SSH password update failed (exit %s): %s",
                result.returncode,
                result.stderr.strip(),
            )
    except FileNotFoundError:
        logger.warning("sudo not available — SSH password update skipped")
