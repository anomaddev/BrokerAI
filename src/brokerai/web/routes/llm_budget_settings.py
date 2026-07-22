"""LLM budget settings API (kill switch + daily USD cap)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.config.settings import get_settings
from brokerai.cost.llm_guard import get_budget_settings, update_budget_settings
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/settings/llm-budget", tags=["settings-llm-budget"])


class LlmBudgetBody(BaseModel):
    kill_switch: bool | None = None
    daily_limit_usd: float | None = Field(default=None, ge=0, le=10000)


@router.get("")
async def get_llm_budget(_username: str = Depends(require_auth)) -> JSONResponse:
    doc = await get_budget_settings()
    doc["env_kill_switch"] = bool(get_settings().llm_kill_switch)
    return JSONResponse(doc)


@router.put("")
async def put_llm_budget(
    body: LlmBudgetBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    doc = await update_budget_settings(
        kill_switch=body.kill_switch,
        daily_limit_usd=body.daily_limit_usd,
    )
    doc["env_kill_switch"] = bool(get_settings().llm_kill_switch)
    return JSONResponse(doc)
