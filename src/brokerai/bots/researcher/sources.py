from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from brokerai.bots.researcher.news import (
    fetch_news_for_queries,
    fetch_news_via_web_search,
    fetch_news_via_x_search,
)
from brokerai.bots.researcher.prompts import news_queries_for_group
from brokerai.bots.researcher.rss import fetch_rss_articles, filter_articles_for_group
from brokerai.bots.researcher.rss_feeds import normalize_rss_categories
from brokerai.provider_capabilities import supports_capability

logger = logging.getLogger(__name__)

# Upper bound on merged articles fed into a single analysis prompt.
MAX_GROUP_ARTICLES = 18


@dataclass
class SearchSource:
    model: dict
    capability: str


@dataclass
class ResolvedSources:
    newsapi_enabled: bool = False
    newsapi_key: str = ""
    rss_enabled: bool = False
    rss_categories: dict[str, bool] | None = None
    web_search: SearchSource | None = None
    x_search: SearchSource | None = None
    rss_articles: list[dict] | None = None

    @property
    def any_active(self) -> bool:
        return bool(
            (self.newsapi_enabled and self.newsapi_key)
            or self.rss_enabled
            or self.web_search
            or self.x_search
        )

    def describe(self) -> list[str]:
        active: list[str] = []
        if self.newsapi_enabled and self.newsapi_key:
            active.append("NewsAPI")
        if self.rss_enabled:
            active.append("RSS")
        if self.web_search:
            active.append(f"web search ({_model_label(self.web_search.model)})")
        if self.x_search:
            active.append(f"X search ({_model_label(self.x_search.model)})")
        return active


def _model_label(model: dict) -> str:
    return model.get("title") or model.get("model_name") or model.get("id") or "model"


def _resolve_search(
    *,
    enabled: bool,
    model_id: str | None,
    capability: str,
    capabilities_map: dict[str, dict[str, bool]],
    models_by_id: dict[str, dict],
) -> SearchSource | None:
    if not enabled or not model_id:
        return None
    model = models_by_id.get(model_id)
    if not model:
        logger.warning("Data source %s references unknown model %s", capability, model_id)
        return None
    if not model.get("enabled"):
        logger.warning("Data source %s model %s is disabled", capability, model_id)
        return None
    if not model.get("api_key"):
        logger.warning("Data source %s model %s has no API key", capability, model_id)
        return None
    if not supports_capability(str(model.get("type") or ""), capability):
        logger.warning(
            "Data source %s not supported by model type %s", capability, model.get("type")
        )
        return None
    if not capabilities_map.get(model_id, {}).get(capability):
        logger.warning("Capability %s not enabled for model %s", capability, model_id)
        return None
    return SearchSource(model=model, capability=capability)


def resolve_sources(
    *,
    data_sources: dict,
    newsapi_doc: dict,
    capabilities_map: dict[str, dict[str, bool]],
    models_by_id: dict[str, dict],
) -> ResolvedSources:
    resolved = ResolvedSources()
    if (
        data_sources.get("newsapi")
        and newsapi_doc.get("enabled")
        and newsapi_doc.get("api_key")
    ):
        resolved.newsapi_enabled = True
        resolved.newsapi_key = str(newsapi_doc["api_key"])

    resolved.web_search = _resolve_search(
        enabled=bool(data_sources.get("web_search_enabled")),
        model_id=data_sources.get("web_search_model_id"),
        capability="web_search",
        capabilities_map=capabilities_map,
        models_by_id=models_by_id,
    )
    resolved.x_search = _resolve_search(
        enabled=bool(data_sources.get("x_search_enabled")),
        model_id=data_sources.get("x_search_model_id"),
        capability="x_search",
        capabilities_map=capabilities_map,
        models_by_id=models_by_id,
    )
    resolved.rss_enabled = bool(data_sources.get("rss_enabled"))
    resolved.rss_categories = normalize_rss_categories(data_sources.get("rss_categories"))
    return resolved


def _merge_articles(
    collected: list[tuple[str, list[dict]]],
    *,
    limit: int,
) -> list[dict]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    merged: list[dict] = []
    for source_name, articles in collected:
        for article in articles:
            url = (article.get("url") or "").strip().lower().rstrip("/")
            title = (article.get("title") or "").strip().lower()
            if url and url in seen_urls:
                continue
            if not url and title and title in seen_titles:
                continue
            if url:
                seen_urls.add(url)
            if title:
                seen_titles.add(title)
            merged.append({**article, "data_source": source_name})
            if len(merged) >= limit:
                return merged
    return merged


async def fetch_group_articles(
    sources: ResolvedSources,
    primary: str,
    group_pairs: list[str],
    *,
    page_size: int = 10,
) -> tuple[list[dict], list[str]]:
    """Fetch articles for one currency group from all active sources in parallel."""
    notes: list[str] = []

    async def _run_newsapi() -> tuple[str, list[dict]]:
        queries = news_queries_for_group(primary, group_pairs)
        articles, _ = await fetch_news_for_queries(
            sources.newsapi_key, queries, page_size=page_size
        )
        return "NewsAPI", articles

    async def _run_web() -> tuple[str, list[dict]]:
        model = sources.web_search.model
        articles = await fetch_news_via_web_search(
            model["base_url"],
            model["model_name"],
            model.get("api_key") or "",
            primary,
            group_pairs,
            page_size=page_size,
        )
        return "web search", articles

    async def _run_x() -> tuple[str, list[dict]]:
        model = sources.x_search.model
        articles = await fetch_news_via_x_search(
            model["base_url"],
            model["model_name"],
            model.get("api_key") or "",
            primary,
            group_pairs,
            page_size=page_size,
        )
        return "X search", articles

    async def _run_rss() -> tuple[str, list[dict]]:
        if sources.rss_articles is not None:
            articles = filter_articles_for_group(
                sources.rss_articles,
                primary,
                group_pairs,
                limit=page_size,
            )
            return "RSS", articles
        articles, notes = await fetch_rss_articles(categories=sources.rss_categories)
        if notes:
            logger.info("RSS prefetch for %s: %s", primary, "; ".join(notes))
        filtered = filter_articles_for_group(
            articles,
            primary,
            group_pairs,
            limit=page_size,
        )
        return "RSS", filtered

    jobs: list[tuple[str, "asyncio.Future"]] = []
    if sources.newsapi_enabled and sources.newsapi_key:
        jobs.append(("NewsAPI", _run_newsapi()))
    if sources.rss_enabled:
        jobs.append(("RSS", _run_rss()))
    if sources.web_search:
        jobs.append(("Web search", _run_web()))
    if sources.x_search:
        jobs.append(("X search", _run_x()))

    if not jobs:
        return [], ["no data sources active"]

    results = await asyncio.gather(*(job for _, job in jobs), return_exceptions=True)

    collected: list[tuple[str, list[dict]]] = []
    for (label, _), result in zip(jobs, results):
        if isinstance(result, Exception):
            logger.warning("%s failed for %s group: %s", label, primary, result)
            notes.append(f"{label} failed: {result}")
            continue
        source_name, articles = result
        if articles:
            collected.append((source_name, articles))
        else:
            notes.append(f"{label} returned no articles")

    merged = _merge_articles(collected, limit=MAX_GROUP_ARTICLES)
    return merged, notes
