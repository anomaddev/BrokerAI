from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.config_backup.change_labels import describe_asset_settings_change
from brokerai.config_backup.hooks import auto_backup_before
from brokerai.db.repositories.asset_settings import ASSET_CLASSES, AssetSettingsRepository
from brokerai.market_sessions import TRADING_SESSIONS, session_definition_payload
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/settings/assets", tags=["settings-assets"])


class AssetSettingsBody(BaseModel):
    enabled: bool
    enabled_pairs: list[str] | None = None
    pair_order: list[str] | None = None
    enabled_sessions: dict[str, bool] | None = None
    primary_exchange: str | None = None


def _forex_sessions_payload() -> list[dict[str, str | int | None]]:
    return [session_definition_payload(session) for session in TRADING_SESSIONS]


@router.get("/forex/pairs")
async def get_forex_pairs(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = AssetSettingsRepository()
    settings = await repo.get("forex")
    return JSONResponse(
        {
            "catalog": repo.forex_catalog(),
            "enabled_pairs": settings.get("enabled_pairs") or [],
            "pair_order": settings.get("pair_order") or [],
            "enabled": bool(settings.get("enabled")),
            "primary_exchange": settings.get("primary_exchange"),
            "enabled_sessions": settings.get("enabled_sessions") or {},
            "sessions": _forex_sessions_payload(),
        }
    )


@router.get("/{asset_class}")
async def get_asset_settings(
    asset_class: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    if asset_class not in ASSET_CLASSES:
        raise HTTPException(status_code=404, detail="Unknown asset class")
    repo = AssetSettingsRepository()
    return JSONResponse(await repo.get(asset_class))


@router.put("/{asset_class}")
async def save_asset_settings(
    asset_class: str,
    body: AssetSettingsBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    if asset_class not in ASSET_CLASSES:
        raise HTTPException(status_code=404, detail="Unknown asset class")

    repo = AssetSettingsRepository()
    current = await repo.get(asset_class)
    change_label = describe_asset_settings_change(
        asset_class,
        current,
        enabled=body.enabled,
        enabled_sessions=body.enabled_sessions,
        enabled_pairs=body.enabled_pairs if asset_class == "forex" else None,
        pair_order=body.pair_order if asset_class == "forex" else None,
        primary_exchange=body.primary_exchange,
    )
    await auto_backup_before(
        trigger=f"asset_settings.{asset_class}",
        summary=f"{asset_class.title()} asset settings",
        change_label=change_label or f"{asset_class.title()} asset settings",
    )

    try:
        doc = await repo.save(
            asset_class,
            enabled=body.enabled,
            enabled_pairs=body.enabled_pairs if asset_class == "forex" else None,
            pair_order=body.pair_order if asset_class == "forex" else None,
            enabled_sessions=body.enabled_sessions if asset_class == "forex" else None,
            primary_exchange=body.primary_exchange,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(doc)
