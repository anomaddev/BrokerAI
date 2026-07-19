"""First-run onboarding progress API (UI wizard resume + complete)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from brokerai.auth import AuthStore
from brokerai.auth.onboarding import (
    ONBOARDING_STEPS,
    OnboardingStep,
    OnboardingStore,
    resolve_onboarding_status,
)
from brokerai.config.settings import get_settings
from brokerai.web.routes.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class OnboardingProgressBody(BaseModel):
    current_step: OnboardingStep | None = None
    selected_exchange_id: str | None = None
    enabled_pairs: list[str] | None = None
    strategy_id: str | None = None
    strategy_name: str | None = None
    clear_selected_exchange: bool = False


@router.get("/status")
async def onboarding_status() -> dict[str, object]:
    store = AuthStore()
    return resolve_onboarding_status(auth_complete=store.is_setup_complete())


@router.put("/progress")
async def update_onboarding_progress(
    body: OnboardingProgressBody,
    _username: str = Depends(require_auth),
) -> dict[str, object]:
    auth = AuthStore()
    if not auth.is_setup_complete():
        raise HTTPException(status_code=400, detail="Admin setup required first")

    if body.current_step is not None and body.current_step not in ONBOARDING_STEPS:
        raise HTTPException(status_code=400, detail="Invalid onboarding step")
    if body.current_step == "admin":
        raise HTTPException(status_code=400, detail="Cannot set progress to admin")

    store = OnboardingStore()
    try:
        store.update_progress(
            current_step=body.current_step,
            selected_exchange_id=body.selected_exchange_id,
            enabled_pairs=body.enabled_pairs,
            strategy_id=body.strategy_id,
            strategy_name=body.strategy_name,
            clear_selected_exchange=body.clear_selected_exchange,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return resolve_onboarding_status(auth_complete=True)


async def _verify_setup_persisted(auth: AuthStore) -> dict[str, bool | None]:
    """Confirm admin profile + onboarding (and optional exchange/instruments) are durable."""
    user = auth.get_user()
    if user is None or not user.username:
        raise HTTPException(status_code=500, detail="Admin profile is missing")

    checks: dict[str, bool | None] = {
        "profile": True,
        "onboarding": None,
        "exchange": None,
        "instruments": None,
    }

    settings = get_settings()
    if settings.use_postgres:
        from brokerai.auth.pg_profile import load_onboarding, load_user_profile

        profile = load_user_profile()
        if profile is None or not profile.get("username") or not profile.get("_setup_complete"):
            raise HTTPException(
                status_code=500,
                detail="Admin profile was not found in the database",
            )
        if str(profile.get("username")) != user.username:
            raise HTTPException(
                status_code=500,
                detail="Stored admin profile does not match the signed-in user",
            )
        checks["profile"] = True

    onboarding = OnboardingStore()
    try:
        onboarding.update_progress(current_step="finish")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    persisted = onboarding._read()
    if persisted is None or persisted.current_step != "finish":
        raise HTTPException(
            status_code=500,
            detail="Onboarding progress could not be confirmed in storage",
        )
    checks["onboarding"] = True

    if settings.use_postgres:
        from brokerai.auth.pg_profile import load_onboarding

        pg_doc = load_onboarding()
        if not pg_doc or pg_doc.get("current_step") != "finish":
            raise HTTPException(
                status_code=500,
                detail="Onboarding progress was not found in the database",
            )

    if settings.use_postgres and persisted.selected_exchange_id:
        from brokerai.db.repositories.exchange_connections import (
            OANDA_ID,
            ExchangeConnectionsRepository,
        )

        repo = ExchangeConnectionsRepository()
        connection = await repo.get_connection(persisted.selected_exchange_id)
        if persisted.selected_exchange_id == OANDA_ID:
            connected = ExchangeConnectionsRepository.public_oanda(connection).get("connected")
        else:
            connected = bool(connection.get("access_token") or connection.get("api_key"))
        if not connected:
            raise HTTPException(
                status_code=500,
                detail=f"Exchange '{persisted.selected_exchange_id}' was not saved",
            )
        checks["exchange"] = True

    if settings.use_postgres and persisted.enabled_pairs:
        from brokerai.db.repositories.asset_settings import AssetSettingsRepository

        forex = await AssetSettingsRepository().get("forex")
        saved_pairs = set(forex.get("enabled_pairs") or [])
        missing = [pair for pair in persisted.enabled_pairs if pair not in saved_pairs]
        if missing:
            raise HTTPException(
                status_code=500,
                detail="Instrument selections were not saved",
            )
        checks["instruments"] = True

    return checks


@router.post("/verify")
async def verify_onboarding(_username: str = Depends(require_auth)) -> dict[str, object]:
    """Persist finish step and confirm setup rows are readable from storage/Supabase."""
    auth = AuthStore()
    if not auth.is_setup_complete():
        raise HTTPException(status_code=400, detail="Admin setup required first")

    checks = await _verify_setup_persisted(auth)
    payload = resolve_onboarding_status(auth_complete=True)
    payload["verified"] = True
    payload["checks"] = checks
    return payload


@router.post("/complete")
async def complete_onboarding(_username: str = Depends(require_auth)) -> dict[str, object]:
    """Mark onboarding finished. Exchange/strategy setup may continue from the dashboard."""
    auth = AuthStore()
    if not auth.is_setup_complete():
        raise HTTPException(status_code=400, detail="Admin setup required first")

    user = auth.get_user()
    if user is None:
        raise HTTPException(status_code=500, detail="Admin profile is missing")

    store = OnboardingStore()
    store.mark_complete()
    logger.info("Onboarding completed — bot start still requires enabled asset + strategy")
    return resolve_onboarding_status(auth_complete=True)
