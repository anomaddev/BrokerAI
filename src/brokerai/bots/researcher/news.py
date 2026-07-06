from __future__ import annotations

import json
import logging
import re
import sys
from urllib.parse import urlencode

import httpx

from brokerai.bots.researcher.llm import grok_web_search, grok_x_search

logger = logging.getLogger(__name__)

NEWSAPI_BASE = "https://newsapi.org/v2"


async def test_newsapi(api_key: str) -> tuple[bool, str]:
    if not api_key.strip():
        return False, "NewsAPI key is not configured"

    url = f"{NEWSAPI_BASE}/top-headlines"
    params = {"country": "us", "pageSize": 1, "apiKey": api_key.strip()}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            if response.status_code == 401:
                return False, "Invalid NewsAPI key"
            if response.status_code != 200:
                return False, f"NewsAPI returned HTTP {response.status_code}"
            data = response.json()
            if data.get("status") != "ok":
                return False, data.get("message", "NewsAPI request failed")
            return True, "NewsAPI connection successful"
    except httpx.HTTPError as exc:
        return False, f"NewsAPI request failed: {exc}"


async def fetch_news_for_query(api_key: str, query: str, *, page_size: int = 10) -> list[dict]:
    url = f"{NEWSAPI_BASE}/everything"
    key = api_key.strip()
    params = {
        "q": query,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": page_size,
        "apiKey": key,
    }
    debug_params = {**params, "apiKey": "***"}
    search_url = f"{url}?{urlencode(debug_params)}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "ok":
            raise RuntimeError(data.get("message", "NewsAPI request failed"))
        articles = data.get("articles") or []
        normalized = [
            {
                "title": a.get("title") or "",
                "url": a.get("url") or "",
                "source": (a.get("source") or {}).get("name") or "",
                "publishedAt": a.get("publishedAt") or "",
                "description": a.get("description") or "",
            }
            for a in articles
            if a.get("title")
        ]
        logger.debug(
            "NewsAPI search: %s — %d raw articles, %d with titles",
            search_url,
            len(articles),
            len(normalized),
        )
        print(
            f"NewsAPI: {search_url} — {len(articles)} articles found "
            f"({len(normalized)} with titles)",
            file=sys.stderr,
        )
        return normalized


async def fetch_news_for_queries(
    api_key: str,
    queries: list[str],
    *,
    page_size: int = 10,
) -> tuple[list[dict], str | None]:
    """Try NewsAPI queries in order until articles are found."""
    last_query: str | None = None
    for query in queries:
        last_query = query
        articles = await fetch_news_for_query(api_key, query, page_size=page_size)
        if articles:
            return articles, query
    return [], last_query


def _parse_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return json.loads(stripped)


def _normalize_grok_articles(raw_articles: list) -> list[dict]:
    normalized: list[dict] = []
    for item in raw_articles:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        normalized.append(
            {
                "title": title,
                "url": (item.get("url") or "").strip(),
                "source": (item.get("source") or "").strip(),
                "publishedAt": (item.get("publishedAt") or "").strip(),
                "description": (item.get("description") or "").strip(),
            }
        )
    return normalized


_WEB_SEARCH_PROMPT = (
    "Search the web for recent forex news from the past 7 days relevant to the "
    "{primary} currency group, especially these pairs: {pair_list}.\n\n"
    "Find up to {page_size} credible articles from established financial news "
    "sources (e.g. Reuters, Bloomberg, FT, central bank releases).\n\n"
    "Return ONLY a JSON object with this shape (no markdown, no commentary):\n"
    '{{"articles": [{{"title": "...", "url": "...", "source": "...", '
    '"description": "...", "publishedAt": "..."}}]}}\n\n'
    "Use empty strings for unknown fields. publishedAt should be ISO-8601 when known."
)

_X_SEARCH_PROMPT = (
    "Search X (formerly Twitter) for recent posts from the past 7 days relevant to "
    "the {primary} currency group, especially these pairs: {pair_list}.\n\n"
    "Prioritise credible market analysts, economists, financial journalists, and "
    "official accounts. Find up to {page_size} substantive posts and summarise each "
    "as a news item.\n\n"
    "Return ONLY a JSON object with this shape (no markdown, no commentary):\n"
    '{{"articles": [{{"title": "...", "url": "...", "source": "...", '
    '"description": "...", "publishedAt": "..."}}]}}\n\n'
    "Use the post URL for url, the author handle for source, and a one-line summary "
    "for description. publishedAt should be ISO-8601 when known; use empty strings "
    "for unknown fields."
)


async def _fetch_via_search(
    search_fn,
    *,
    base_url: str,
    model_name: str,
    api_key: str,
    primary: str,
    pairs: list[str],
    page_size: int,
    reasoning_effort: str | None,
    prompt_template: str,
    label: str,
) -> list[dict]:
    pair_list = ", ".join(pairs)
    prompt = prompt_template.format(primary=primary, pair_list=pair_list, page_size=page_size)
    print(
        f"{label}: {base_url.rstrip('/')}/responses (model={model_name}) — pairs: {pair_list}",
        file=sys.stderr,
    )

    operation = "web_search" if label == "Web search" else "x_search"
    text = await search_fn(
        base_url,
        model_name,
        api_key,
        [{"role": "user", "content": prompt}],
        reasoning_effort=reasoning_effort,
        cost_context={
            "operation": operation,
            "source": "daily_report",
            "forex_group": primary,
        },
    )
    data = _parse_json_object(text)
    articles = data.get("articles") if isinstance(data, dict) else None
    if not isinstance(articles, list):
        raise RuntimeError(f"{label} did not return an articles array")

    normalized = _normalize_grok_articles(articles)
    print(
        f"{label}: {len(normalized)} articles found for {primary} group",
        file=sys.stderr,
    )
    return normalized[:page_size]


async def fetch_news_via_web_search(
    base_url: str,
    model_name: str,
    api_key: str,
    primary: str,
    pairs: list[str],
    *,
    page_size: int = 10,
    reasoning_effort: str | None = None,
) -> list[dict]:
    """Find forex news via a model's web search capability."""
    return await _fetch_via_search(
        grok_web_search,
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        primary=primary,
        pairs=pairs,
        page_size=page_size,
        reasoning_effort=reasoning_effort,
        prompt_template=_WEB_SEARCH_PROMPT,
        label="Web search",
    )


async def fetch_news_via_x_search(
    base_url: str,
    model_name: str,
    api_key: str,
    primary: str,
    pairs: list[str],
    *,
    page_size: int = 10,
    reasoning_effort: str | None = None,
) -> list[dict]:
    """Find forex commentary via a model's X (Twitter) search capability."""
    return await _fetch_via_search(
        grok_x_search,
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        primary=primary,
        pairs=pairs,
        page_size=page_size,
        reasoning_effort=reasoning_effort,
        prompt_template=_X_SEARCH_PROMPT,
        label="X search",
    )
