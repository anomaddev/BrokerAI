from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.bots.researcher.prompts import (
    get_weekly_brief_prompt_preview,
    get_weekly_debrief_prompt_preview,
)
from brokerai.provider_capabilities import supports_capability
from brokerai.research_markets import (
    MAX_DAILY_REPORT_MARKET_OFFSET_HOURS,
    MIN_DAILY_REPORT_MARKET_OFFSET_HOURS,
    collect_schedule_warnings,
    describe_close_schedule,
    describe_schedule,
    get_market,
    list_schedule_markets,
    normalize_market_id,
    normalize_market_offset_hours,
)
from brokerai.research_constants import DAILY_REPORT_REASONING_EFFORT, REASONING_EFFORT_OPTIONS
from brokerai.db.repositories.ai_models import AiModelsRepository
from brokerai.db.repositories.data_connections import DataConnectionsRepository
from brokerai.db.repositories.research_settings import ResearchSettingsRepository
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/settings/research", tags=["settings-research"])


class ContributorModelBody(BaseModel):
    model_id: str
    reasoning_effort: str = DAILY_REPORT_REASONING_EFFORT
    enabled: bool = True


class DataSourcesBody(BaseModel):
    newsapi: bool = True
    web_search_enabled: bool = False
    web_search_model_id: str | None = None
    x_search_enabled: bool = False
    x_search_model_id: str | None = None


class ResearchSettingsBody(BaseModel):
    contributor_models: list[ContributorModelBody] = Field(default_factory=list)
    synthesis_model_id: str | None = None
    synthesis_reasoning_effort: str | None = None
    data_sources: DataSourcesBody | None = None
    daily_report_enabled: bool | None = None
    daily_report_market_id: str | None = None
    daily_report_market_offset_hours: int | None = None


class WeeklyResearchSettingsBody(BaseModel):
    weekly_brief_enabled: bool | None = None
    weekly_brief_model_id: str | None = None
    weekly_brief_reasoning_effort: str | None = None
    weekly_brief_market_id: str | None = None
    weekly_brief_market_offset_hours: int | None = None
    weekly_debrief_enabled: bool | None = None
    weekly_debrief_model_id: str | None = None
    weekly_debrief_reasoning_effort: str | None = None
    weekly_debrief_market_id: str | None = None
    weekly_debrief_market_offset_hours: int | None = None


def _check_effort(value: str | None) -> None:
    if value is not None and value not in REASONING_EFFORT_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid reasoning_effort. Must be one of: {', '.join(sorted(REASONING_EFFORT_OPTIONS))}",
        )


def _check_offset(offset: int | None, field_name: str) -> None:
    if offset is None:
        return
    if offset < MIN_DAILY_REPORT_MARKET_OFFSET_HOURS or offset > MAX_DAILY_REPORT_MARKET_OFFSET_HOURS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field_name} must be between "
                f"{MIN_DAILY_REPORT_MARKET_OFFSET_HOURS} and "
                f"{MAX_DAILY_REPORT_MARKET_OFFSET_HOURS}"
            ),
        )


def _enrich_settings_payload(settings: dict) -> dict:
    schedule_warnings = collect_schedule_warnings(
        daily_report_enabled=settings.get("daily_report_enabled", False),
        daily_report_market_id=settings.get("daily_report_market_id", "london"),
        daily_report_market_offset_hours=settings.get("daily_report_market_offset_hours", -2),
        weekly_brief_enabled=settings.get("weekly_brief_enabled", False),
        weekly_brief_market_id=settings.get("weekly_brief_market_id", "london"),
        weekly_brief_market_offset_hours=settings.get("weekly_brief_market_offset_hours", -1),
    )
    brief_preview = get_weekly_brief_prompt_preview()
    debrief_preview = get_weekly_debrief_prompt_preview()
    return {
        **settings,
        "schedule_markets": list_schedule_markets(),
        "schedule_description": describe_schedule(
            settings.get("daily_report_market_id", "london"),
            settings.get("daily_report_market_offset_hours", -2),
        ),
        "weekly_brief_schedule_description": describe_schedule(
            settings.get("weekly_brief_market_id", "london"),
            settings.get("weekly_brief_market_offset_hours", -1),
        ),
        "weekly_debrief_schedule_description": describe_close_schedule(
            settings.get("weekly_debrief_market_id", "london"),
            settings.get("weekly_debrief_market_offset_hours", 1),
        ),
        "schedule_warnings": schedule_warnings,
        "weekly_brief_prompt_preview": brief_preview,
        "weekly_debrief_prompt_preview": debrief_preview,
    }


@router.get("")
async def get_research_settings(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = ResearchSettingsRepository()
    settings = await repo.get()
    return JSONResponse(_enrich_settings_payload(settings))


@router.put("")
async def save_research_settings(
    body: ResearchSettingsBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    models_repo = AiModelsRepository()
    connections_repo = DataConnectionsRepository()

    contributors: list[dict] = []
    for entry in body.contributor_models:
        model = await models_repo.find_by_id(entry.model_id)
        if not model:
            raise HTTPException(status_code=400, detail=f"Model not found: {entry.model_id}")
        if not model.get("enabled"):
            raise HTTPException(status_code=400, detail=f"Model is disabled: {model.get('title')}")
        _check_effort(entry.reasoning_effort)
        contributors.append(
            {
                "model_id": entry.model_id,
                "reasoning_effort": entry.reasoning_effort,
                "enabled": entry.enabled,
            }
        )

    if body.synthesis_model_id:
        model = await models_repo.find_by_id(body.synthesis_model_id)
        if not model:
            raise HTTPException(
                status_code=400, detail=f"Synthesis model not found: {body.synthesis_model_id}"
            )
        if not model.get("enabled"):
            raise HTTPException(
                status_code=400, detail=f"Synthesis model is disabled: {model.get('title')}"
            )

    _check_effort(body.synthesis_reasoning_effort)

    if body.daily_report_market_id is not None and not get_market(body.daily_report_market_id):
        raise HTTPException(status_code=400, detail=f"Unknown market: {body.daily_report_market_id}")

    _check_offset(body.daily_report_market_offset_hours, "daily_report_market_offset_hours")

    if body.data_sources is not None:
        await _validate_source_model(
            connections_repo,
            models_repo,
            enabled=body.data_sources.web_search_enabled,
            model_id=body.data_sources.web_search_model_id,
            capability="web_search",
            label="Web search",
        )
        await _validate_source_model(
            connections_repo,
            models_repo,
            enabled=body.data_sources.x_search_enabled,
            model_id=body.data_sources.x_search_model_id,
            capability="x_search",
            label="X search",
        )

    repo = ResearchSettingsRepository()
    settings = await repo.save(
        contributor_models=contributors,
        synthesis_model_id=body.synthesis_model_id,
        synthesis_reasoning_effort=body.synthesis_reasoning_effort,
        data_sources=body.data_sources.model_dump() if body.data_sources else None,
        daily_report_enabled=body.daily_report_enabled,
        daily_report_market_id=normalize_market_id(body.daily_report_market_id)
        if body.daily_report_market_id is not None
        else None,
        daily_report_market_offset_hours=normalize_market_offset_hours(
            body.daily_report_market_offset_hours
        )
        if body.daily_report_market_offset_hours is not None
        else None,
    )
    return JSONResponse(_enrich_settings_payload(settings))


@router.put("/weekly")
async def save_weekly_research_settings(
    body: WeeklyResearchSettingsBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    models_repo = AiModelsRepository()

    for model_id, label in (
        (body.weekly_brief_model_id, "Weekly brief"),
        (body.weekly_debrief_model_id, "Weekly debrief"),
    ):
        if model_id:
            model = await models_repo.find_by_id(model_id)
            if not model:
                raise HTTPException(status_code=400, detail=f"{label} model not found")
            if not model.get("enabled"):
                raise HTTPException(status_code=400, detail=f"{label} model is disabled")

    _check_effort(body.weekly_brief_reasoning_effort)
    _check_effort(body.weekly_debrief_reasoning_effort)

    for market_id, label in (
        (body.weekly_brief_market_id, "Weekly brief"),
        (body.weekly_debrief_market_id, "Weekly debrief"),
    ):
        if market_id is not None and not get_market(market_id):
            raise HTTPException(status_code=400, detail=f"Unknown market for {label}")

    _check_offset(body.weekly_brief_market_offset_hours, "weekly_brief_market_offset_hours")
    _check_offset(body.weekly_debrief_market_offset_hours, "weekly_debrief_market_offset_hours")

    repo = ResearchSettingsRepository()
    settings = await repo.save(
        weekly_brief_enabled=body.weekly_brief_enabled,
        weekly_brief_model_id=body.weekly_brief_model_id,
        weekly_brief_reasoning_effort=body.weekly_brief_reasoning_effort,
        weekly_brief_market_id=normalize_market_id(body.weekly_brief_market_id)
        if body.weekly_brief_market_id is not None
        else None,
        weekly_brief_market_offset_hours=normalize_market_offset_hours(
            body.weekly_brief_market_offset_hours
        )
        if body.weekly_brief_market_offset_hours is not None
        else None,
        weekly_debrief_enabled=body.weekly_debrief_enabled,
        weekly_debrief_model_id=body.weekly_debrief_model_id,
        weekly_debrief_reasoning_effort=body.weekly_debrief_reasoning_effort,
        weekly_debrief_market_id=normalize_market_id(body.weekly_debrief_market_id)
        if body.weekly_debrief_market_id is not None
        else None,
        weekly_debrief_market_offset_hours=normalize_market_offset_hours(
            body.weekly_debrief_market_offset_hours
        )
        if body.weekly_debrief_market_offset_hours is not None
        else None,
    )
    return JSONResponse(_enrich_settings_payload(settings))


async def _validate_source_model(
    connections_repo: DataConnectionsRepository,
    models_repo: AiModelsRepository,
    *,
    enabled: bool,
    model_id: str | None,
    capability: str,
    label: str,
) -> None:
    if not enabled:
        return
    if not model_id:
        raise HTTPException(status_code=400, detail=f"{label} is enabled but no model is selected")

    model = await models_repo.find_by_id(model_id)
    if not model:
        raise HTTPException(status_code=400, detail=f"{label} model not found")
    if not model.get("enabled"):
        raise HTTPException(status_code=400, detail=f"{label} model is disabled")
    if not supports_capability(str(model.get("type") or ""), capability):
        raise HTTPException(
            status_code=400,
            detail=f"{label} is not supported by {model.get('title') or model.get('model_name')}",
        )
    caps = await connections_repo.get_model_capabilities(model_id)
    if not caps.get(capability):
        raise HTTPException(
            status_code=400,
            detail=f"{label} capability is not enabled for {model.get('title') or model.get('model_name')}",
        )
