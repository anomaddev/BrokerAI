from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel, Field

from brokerai.bots.researcher.rss_feeds import feeds_for_api, feeds_to_opml, normalize_rss_categories
from brokerai.db.repositories.research_settings import ResearchSettingsRepository
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/settings/rss-feeds", tags=["settings-rss-feeds"])


class RssCategoriesBody(BaseModel):
    rss_enabled: bool | None = None
    rss_categories: dict[str, bool] = Field(default_factory=dict)


@router.get("")
async def get_rss_feeds(_username: str = Depends(require_auth)) -> JSONResponse:
    settings = await ResearchSettingsRepository().get()
    sources = settings.get("data_sources") or {}
    categories = normalize_rss_categories(sources.get("rss_categories"))
    payload = feeds_for_api(categories)
    payload["rss_enabled"] = bool(sources.get("rss_enabled"))
    return JSONResponse(payload)


@router.put("")
async def save_rss_feeds(
    body: RssCategoriesBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = ResearchSettingsRepository()
    current = await repo.get()
    sources = dict(current.get("data_sources") or {})

    if body.rss_enabled is not None:
        sources["rss_enabled"] = body.rss_enabled

    if body.rss_categories:
        merged = normalize_rss_categories(sources.get("rss_categories"))
        for key, enabled in body.rss_categories.items():
            if key in merged:
                merged[key] = bool(enabled)
        sources["rss_categories"] = merged

    saved = await repo.save(data_sources=sources)
    categories = normalize_rss_categories(saved["data_sources"].get("rss_categories"))
    payload = feeds_for_api(categories)
    payload["rss_enabled"] = bool(saved["data_sources"].get("rss_enabled"))
    return JSONResponse(payload)


@router.get("/opml")
async def export_rss_opml(_username: str = Depends(require_auth)) -> PlainTextResponse:
    settings = await ResearchSettingsRepository().get()
    sources = settings.get("data_sources") or {}
    categories = normalize_rss_categories(sources.get("rss_categories"))
    content = feeds_to_opml(categories)
    return PlainTextResponse(
        content,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="brokerai-rss-feeds.opml"'},
    )
