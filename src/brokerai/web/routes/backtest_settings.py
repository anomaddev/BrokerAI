"""HTTP routes for backtest processor settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.db.repositories.ai_models import AiModelsRepository
from brokerai.db.repositories.backtest_settings import (
    MAX_CONCURRENT,
    MIN_CONCURRENT,
    BacktestSettingsRepository,
)
from brokerai.research_constants import REASONING_EFFORT_OPTIONS
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/backtest/settings", tags=["backtest-settings"])


class UpdateBacktestSettingsBody(BaseModel):
    max_concurrent: int | None = Field(default=None, ge=MIN_CONCURRENT, le=MAX_CONCURRENT)
    auto_start: bool | None = None
    ai_feedback_enabled: bool | None = None
    ai_feedback_auto_on_complete: bool | None = None
    ai_feedback_model_id: str | None = None
    ai_feedback_model_name: str | None = None
    ai_feedback_reasoning_effort: str | None = None


@router.get("")
async def get_backtest_settings(_username: str = Depends(require_auth)) -> JSONResponse:
    settings = await BacktestSettingsRepository().get()
    return JSONResponse(settings)


@router.put("")
async def update_backtest_settings(
    body: UpdateBacktestSettingsBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    payload = body.model_dump(exclude_unset=True)

    if "ai_feedback_reasoning_effort" in payload:
        effort = payload["ai_feedback_reasoning_effort"]
        if effort is not None and effort not in REASONING_EFFORT_OPTIONS:
            raise HTTPException(status_code=400, detail="Invalid reasoning effort")

    model_id = payload.get("ai_feedback_model_id")
    model_name = payload.get("ai_feedback_model_name")
    if "ai_feedback_model_id" in payload:
        if not model_id:
            payload["ai_feedback_model_id"] = None
            payload["ai_feedback_model_name"] = None
        else:
            source = await AiModelsRepository().find_by_id(model_id)
            if source is None:
                raise HTTPException(status_code=400, detail=f"Model source not found: {model_id}")
            if not source.get("enabled"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Model source is disabled: {source.get('title')}",
                )
            if model_name is not None:
                payload["ai_feedback_model_name"] = (model_name or "").strip() or None

    # Map clear-model to repository flag when id explicitly null.
    clear_model = "ai_feedback_model_id" in payload and not payload.get("ai_feedback_model_id")
    settings = await BacktestSettingsRepository().update(
        max_concurrent=payload.get("max_concurrent"),
        auto_start=payload.get("auto_start"),
        ai_feedback_enabled=payload.get("ai_feedback_enabled"),
        ai_feedback_auto_on_complete=payload.get("ai_feedback_auto_on_complete"),
        ai_feedback_model_id=None if clear_model else payload.get("ai_feedback_model_id"),
        ai_feedback_model_name=None if clear_model else payload.get("ai_feedback_model_name"),
        ai_feedback_reasoning_effort=payload.get("ai_feedback_reasoning_effort"),
        clear_ai_feedback_model=clear_model,
    )
    return JSONResponse(settings)
