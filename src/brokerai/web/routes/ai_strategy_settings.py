"""HTTP routes for AI Strategy settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.db.repositories.ai_strategy_settings import (
    MAX_STARTUP_LOOP_COUNT,
    MAX_STARTUP_TIMEOUT_MINUTES,
    MIN_STARTUP_LOOP_COUNT,
    MIN_STARTUP_TIMEOUT_MINUTES,
    AiStrategySettingsRepository,
)
from brokerai.db.repositories.backtest_runs import BACKTEST_PERIODS
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/settings/ai-strategies", tags=["ai-strategy-settings"])


class UpdateAiStrategySettingsBody(BaseModel):
    startup_enabled: bool | None = None
    startup_loop_count: int | None = Field(
        default=None, ge=MIN_STARTUP_LOOP_COUNT, le=MAX_STARTUP_LOOP_COUNT
    )
    startup_backtest_period: str | None = None
    startup_timeout_minutes: int | None = Field(
        default=None, ge=MIN_STARTUP_TIMEOUT_MINUTES, le=MAX_STARTUP_TIMEOUT_MINUTES
    )


@router.get("")
async def get_ai_strategy_settings(_username: str = Depends(require_auth)) -> JSONResponse:
    settings = await AiStrategySettingsRepository().get()
    return JSONResponse(settings)


@router.put("")
async def update_ai_strategy_settings(
    body: UpdateAiStrategySettingsBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    payload = body.model_dump(exclude_unset=True)
    if "startup_backtest_period" in payload:
        period = payload["startup_backtest_period"]
        if period is not None and period not in BACKTEST_PERIODS:
            raise HTTPException(status_code=400, detail="Invalid backtest period")
    settings = await AiStrategySettingsRepository().update(
        startup_enabled=payload.get("startup_enabled"),
        startup_loop_count=payload.get("startup_loop_count"),
        startup_backtest_period=payload.get("startup_backtest_period"),
        startup_timeout_minutes=payload.get("startup_timeout_minutes"),
    )
    return JSONResponse(settings)
