from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.config_backup.change_labels import describe_strategy_update
from brokerai.config_backup.hooks import auto_backup_before
from brokerai.db.repositories.strategies import StrategiesRepository, clean_instrument_selection
from brokerai.strategies.params import ParamsValidationError
from brokerai.strategies.registry import get_preset, list_presets, serialize_preset
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class CreateStrategyBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=160)
    preset_id: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    instrument_selection: dict[str, list[str]] = Field(default_factory=dict)
    enabled: bool = False


class UpdateStrategyBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=160)
    params: dict[str, Any] | None = None
    instrument_selection: dict[str, list[str]] | None = None
    enabled: bool | None = None


@router.get("/presets")
async def list_strategy_presets(_username: str = Depends(require_auth)) -> JSONResponse:
    presets = [serialize_preset(p) for p in list_presets()]
    return JSONResponse({"presets": presets})


@router.get("")
async def list_strategies(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = StrategiesRepository()
    return JSONResponse({"strategies": await repo.list_all()})


@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = StrategiesRepository()
    doc = await repo.get_by_id(strategy_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return JSONResponse(doc)


@router.post("")
async def create_strategy(
    body: CreateStrategyBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    preset = get_preset(body.preset_id)
    if not preset:
        raise HTTPException(status_code=400, detail="Unknown strategy preset")

    selection = clean_instrument_selection(body.instrument_selection)
    if not selection:
        raise HTTPException(status_code=400, detail="Select at least one instrument")

    await auto_backup_before(
        trigger="strategies.create",
        summary=f"Create strategy: {body.name.strip()}",
        change_label=f"Added strategy: {body.name.strip()}",
    )

    repo = StrategiesRepository()
    try:
        doc = await repo.create(
            name=body.name,
            description=body.description,
            preset_id=body.preset_id,
            params=body.params,
            instrument_selection=selection,
            enabled=body.enabled,
        )
    except ParamsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(doc)


@router.patch("/{strategy_id}")
async def update_strategy(
    strategy_id: str,
    body: UpdateStrategyBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    if (
        body.name is None
        and body.description is None
        and body.params is None
        and body.instrument_selection is None
        and body.enabled is None
    ):
        raise HTTPException(status_code=400, detail="No fields to update")

    selection = None
    if body.instrument_selection is not None:
        selection = clean_instrument_selection(body.instrument_selection)
        if not selection:
            raise HTTPException(status_code=400, detail="Select at least one instrument")

    repo = StrategiesRepository()
    existing = await repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Strategy not found")

    change_label = describe_strategy_update(
        existing,
        name=body.name,
        description=body.description,
        params=body.params,
        instrument_selection=selection,
        enabled=body.enabled,
    )
    await auto_backup_before(
        trigger=f"strategies.patch:{strategy_id}",
        summary=f"Update strategy: {existing.get('name') or strategy_id}",
        change_label=change_label or f"Updated strategy: {existing.get('name') or strategy_id}",
    )

    try:
        doc = await repo.update(
            strategy_id,
            name=body.name,
            description=body.description,
            params=body.params,
            instrument_selection=selection,
            enabled=body.enabled,
        )
    except ParamsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not doc:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return JSONResponse(doc)


@router.delete("/{strategy_id}")
async def delete_strategy(
    strategy_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = StrategiesRepository()
    existing = await repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Strategy not found")

    strategy_name = str(existing.get("name") or strategy_id)
    await auto_backup_before(
        trigger=f"strategies.delete:{strategy_id}",
        summary=f"Delete strategy: {strategy_name}",
        change_label=f"Removed strategy: {strategy_name}",
    )

    deleted = await repo.delete(strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return JSONResponse({"status": "deleted", "id": strategy_id})
