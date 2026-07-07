from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
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
    hash_password,
    is_valid_username,
    normalize_optional_name,
    validate_password,
    verify_password,
)
from brokerai.auth.cookies import delete_session_cookie, set_session_cookie
from brokerai.auth.general_settings import normalize_general_settings
from brokerai.auth.mode import auth_mode, is_builtin_mode, is_oidc_mode
from brokerai.auth.oidc_client import OidcClient
from brokerai.auth.profile_photo import (
    clear_profile_photos,
    resolve_profile_photo_path,
    save_profile_photo,
)
from brokerai.config.settings import get_settings
from brokerai.market_sessions import TRADING_SESSIONS, normalize_market_indicators, session_definition_payload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


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


@router.get("/config")
async def auth_config() -> dict[str, str | bool]:
    store = AuthStore()
    return {
        "mode": auth_mode(),
        "setup_complete": store.is_setup_complete(),
    }


@router.get("/setup/status")
async def setup_status() -> dict[str, bool]:
    return {"setup_complete": AuthStore().is_setup_complete()}


@router.post("/setup")
async def setup(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    profile_photo: UploadFile | None = File(None),
) -> dict[str, str | bool]:
    _reject_when_oidc_enabled()
    store = AuthStore()
    if store.is_setup_complete():
        raise HTTPException(status_code=409, detail="Setup already complete")
    if not is_valid_username(username):
        raise HTTPException(status_code=400, detail="Invalid username")
    try:
        validate_password(password, confirm_password)
    except PasswordValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    profile_photo_name: str | None = None
    if profile_photo and profile_photo.filename:
        try:
            photo_data = await profile_photo.read()
            if photo_data:
                store.ensure_dir()
                profile_photo_name = save_profile_photo(store.auth_dir, photo_data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = store.create_user(username, hash_password(password), profile_photo_name)
    await _provision_ssh_user(username, password)

    token = SessionManager().create_token(record.username)
    set_session_cookie(response, token, request)
    return {
        "username": record.username,
        "status": "created",
        "has_profile_photo": bool(profile_photo_name),
    }


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response) -> dict[str, str]:
    _reject_when_oidc_enabled()
    store = AuthStore()
    if not store.is_setup_complete():
        raise HTTPException(status_code=400, detail="Setup required")
    user = store.get_user()
    if user is None or user.username != body.username:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = SessionManager().create_token(user.username)
    set_session_cookie(response, token, request)
    return {"username": user.username, "status": "ok"}


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    delete_session_cookie(response)
    return {"status": "logged_out"}


@router.get("/oidc/login")
async def oidc_login(request: Request, response: Response) -> Response:
    if not is_oidc_mode():
        raise HTTPException(status_code=404, detail="OIDC auth is not enabled")
    redirect_url = await OidcClient().build_login_redirect(request, response)
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
    response.status_code = 302
    response.headers["Location"] = "/"
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
    has_photo = bool(
        user
        and user.profile_photo
        and resolve_profile_photo_path(store.auth_dir, user.profile_photo)
    )
    mode = auth_mode()
    return {
        "username": username,
        "has_profile_photo": has_photo,
        "first_name": user.first_name if user else None,
        "last_name": user.last_name if user else None,
        "email": user.email if user else None,
        "auth_mode": mode,
        "identity_managed_by_idp": is_oidc_mode(),
    }


@router.get("/profile-photo")
async def get_profile_photo(_username: str = Depends(require_auth)) -> FileResponse:
    store = AuthStore()
    user = store.get_user()
    if user is None:
        raise HTTPException(status_code=404, detail="Profile photo not found")
    path = resolve_profile_photo_path(store.auth_dir, user.profile_photo)
    if path is None:
        raise HTTPException(status_code=404, detail="Profile photo not found")
    return FileResponse(path)


@router.put("/profile-photo")
async def upload_profile_photo(
    file: UploadFile = File(...),
    _username: str = Depends(require_auth),
) -> dict[str, str | bool]:
    store = AuthStore()
    if store.get_user() is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        photo_data = await file.read()
        filename = save_profile_photo(store.auth_dir, photo_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.set_profile_photo(filename)
    return {"status": "ok", "has_profile_photo": True}


@router.delete("/profile-photo")
async def delete_profile_photo(_username: str = Depends(require_auth)) -> dict[str, str | bool]:
    store = AuthStore()
    if store.get_user() is None:
        raise HTTPException(status_code=404, detail="User not found")
    clear_profile_photos(store.auth_dir)
    store.set_profile_photo(None)
    return {"status": "ok", "has_profile_photo": False}


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
    await _provision_ssh_user(record.username, body.current_password)

    token = SessionManager().create_token(record.username)
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
    return {
        "status": "ok",
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
