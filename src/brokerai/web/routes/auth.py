from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from brokerai.auth import (
    AuthStore,
    PasswordValidationError,
    SessionManager,
    hash_password,
    is_valid_username,
    validate_password,
    verify_password,
)
from brokerai.auth.profile_photo import (
    clear_profile_photos,
    resolve_profile_photo_path,
    save_profile_photo,
)
from brokerai.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_max_age,
        path="/",
    )


def get_current_username(request: Request) -> str | None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    return SessionManager().verify_token(token)


async def require_auth(request: Request) -> str:
    username = get_current_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    store = AuthStore()
    user = store.get_user()
    if user is None or user.username != username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return username


@router.get("/setup/status")
async def setup_status() -> dict[str, bool]:
    return {"setup_complete": AuthStore().is_setup_complete()}


@router.post("/setup")
async def setup(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    profile_photo: UploadFile | None = File(None),
) -> dict[str, str | bool]:
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
    _set_session_cookie(response, token)
    return {
        "username": record.username,
        "status": "created",
        "has_profile_photo": bool(profile_photo_name),
    }


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict[str, str]:
    store = AuthStore()
    if not store.is_setup_complete():
        raise HTTPException(status_code=400, detail="Setup required")
    user = store.get_user()
    if user is None or user.username != body.username:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = SessionManager().create_token(user.username)
    _set_session_cookie(response, token)
    return {"username": user.username, "status": "ok"}


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "logged_out"}


@router.get("/me")
async def me(username: str = Depends(require_auth)) -> dict[str, str | bool]:
    store = AuthStore()
    user = store.get_user()
    has_photo = bool(
        user
        and user.profile_photo
        and resolve_profile_photo_path(store.auth_dir, user.profile_photo)
    )
    return {"username": username, "has_profile_photo": has_photo}


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


async def _provision_ssh_user(username: str, password: str) -> None:
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
