from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from brokerai.auth import (
    AuthStore,
    PasswordValidationError,
    SessionManager,
    hash_password,
    validate_password,
    verify_password,
)
from brokerai.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12)
    confirm_password: str = Field(min_length=12)


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
async def setup(body: SetupRequest, response: Response) -> dict[str, str]:
    store = AuthStore()
    if store.is_setup_complete():
        raise HTTPException(status_code=409, detail="Setup already complete")
    try:
        validate_password(body.password, body.confirm_password)
    except PasswordValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = store.create_user(body.username, hash_password(body.password))
    await _provision_ssh_user(body.username, body.password)

    token = SessionManager().create_token(record.username)
    _set_session_cookie(response, token)
    return {"username": record.username, "status": "created"}


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
async def me(username: str = Depends(require_auth)) -> dict[str, str]:
    return {"username": username}


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
