"""Fetch and normalize RSS articles for research runs."""

from __future__ import annotations

import asyncio
import logging
from calendar import timegm
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx

from brokerai.bots.researcher.prompts import news_queries_for_group
from brokerai.bots.researcher.rss_feeds import enabled_feeds

logger = logging.getLogger(__name__)

USER_AGENT = "BrokerAI/1.0 (+https://github.com/brokerai)"
MAX_FEED_ENTRIES = 25
MAX_RSS_ARTICLES = 120

# High-signal macro/geopolitical terms that move FX even without a currency mention.
GLOBAL_MACRO_KEYWORDS = (
    "fomc",
    "federal reserve",
    "fed ",
    "ecb",
    "boe",
    "boj",
    "central bank",
    "interest rate",
    "rate hike",
    "rate cut",
    "inflation",
    "cpi",
    "ppi",
    "gdp",
    "nonfarm",
    "nfp",
    "jobs report",
    "tariff",
    "sanction",
    "geopolit",
    "conflict",
    "war ",
    "election",
    "treasury",
    "yield",
    "bond ",
    "oil ",
    "crude",
    "gold ",
    "forex",
    "currency",
    "exchange rate",
    "ukraine",
    "taiwan",
    "middle east",
    "opec",
)


def _published_iso(entry: Any) -> str:
    """Best-effort ISO-8601 timestamp from a feedparser entry."""
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        try:
            dt = datetime.fromtimestamp(timegm(parsed), tz=timezone.utc)
            return dt.isoformat()
        except (OverflowError, OSError, ValueError):
            pass

    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            continue
    return ""


def _normalize_entry(entry: Any, *, feed_title: str) -> dict[str, str] | None:
    title = (getattr(entry, "title", None) or "").strip()
    if not title:
        return None

    link = (getattr(entry, "link", None) or "").strip()
    description = (
        getattr(entry, "summary", None)
        or getattr(entry, "description", None)
        or ""
    ).strip()
    source = (getattr(entry, "author", None) or feed_title or "").strip()
    return {
        "title": title,
        "url": link,
        "source": source,
        "publishedAt": _published_iso(entry),
        "description": description,
    }


def _dedupe_key(article: dict[str, str]) -> str:
    url = (article.get("url") or "").strip().lower().rstrip("/")
    if url:
        return f"url:{url}"
    title = (article.get("title") or "").strip().lower()
    return f"title:{title}"


def _keywords_for_group(primary: str, pairs: list[str]) -> set[str]:
    """Derive lowercase keyword tokens from NewsAPI query templates."""
    keywords: set[str] = set()
    for query in news_queries_for_group(primary, pairs):
        for token in query.replace('"', " ").replace("(", " ").replace(")", " ").split():
            cleaned = token.strip().lower()
            if len(cleaned) >= 3 and cleaned not in {"and", "or"}:
                keywords.add(cleaned)
    keywords.add(primary.lower())
    for pair in pairs:
        keywords.add(pair.lower())
        if "/" in pair:
            base, quote = pair.split("/", 1)
            keywords.add(base.lower())
            keywords.add(quote.lower())
    return keywords


def article_relevant_to_group(article: dict[str, str], primary: str, pairs: list[str]) -> bool:
    """True when an article mentions the group or a global macro catalyst."""
    text = f"{article.get('title', '')} {article.get('description', '')}".lower()
    if not text.strip():
        return False

    group_keywords = _keywords_for_group(primary, pairs)
    if any(keyword in text for keyword in group_keywords):
        return True

    return any(keyword in text for keyword in GLOBAL_MACRO_KEYWORDS)


def filter_articles_for_group(
    articles: list[dict[str, str]],
    primary: str,
    pairs: list[str],
    *,
    limit: int,
) -> list[dict[str, str]]:
    """Keep articles relevant to a currency group, newest first when timestamps exist."""
    matched = [article for article in articles if article_relevant_to_group(article, primary, pairs)]

    def sort_key(article: dict[str, str]) -> tuple[int, str]:
        published = article.get("publishedAt") or ""
        return (1 if published else 0, published)

    matched.sort(key=sort_key, reverse=True)
    return matched[:limit]


async def _fetch_single_feed(
    client: httpx.AsyncClient,
    feed: dict[str, str],
) -> tuple[str, list[dict[str, str]], str | None]:
    url = feed["url"]
    try:
        response = await client.get(url)
        response.raise_for_status()
        parsed = feedparser.parse(response.text)
        feed_title = (parsed.feed.get("title") if parsed.feed else None) or feed["title"]
        entries = list(parsed.entries or [])[:MAX_FEED_ENTRIES]
        articles = [
            normalized
            for entry in entries
            if (normalized := _normalize_entry(entry, feed_title=feed_title))
        ]
        return feed["id"], articles, None
    except Exception as exc:
        logger.warning("RSS feed %s (%s) failed: %s", feed["title"], url, exc)
        return feed["id"], [], str(exc)


async def fetch_rss_articles(
    *,
    categories: dict[str, bool] | None = None,
    concurrency: int = 8,
) -> tuple[list[dict[str, str]], list[str]]:
    """Fetch all enabled catalog feeds once and return deduplicated articles."""
    feeds = enabled_feeds(categories)
    if not feeds:
        return [], ["no RSS categories enabled"]

    semaphore = asyncio.Semaphore(max(1, concurrency))
    notes: list[str] = []

    async def run(feed: dict[str, str]) -> tuple[str, list[dict[str, str]], str | None]:
        async with semaphore:
            return await _fetch_single_feed(client, feed)

    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
        results = await asyncio.gather(*(run(feed) for feed in feeds), return_exceptions=True)

    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    for result in results:
        if isinstance(result, Exception):
            notes.append(f"RSS fetch failed: {result}")
            continue
        feed_id, articles, error = result
        if error:
            notes.append(f"{feed_id}: {error}")
        for article in articles:
            key = _dedupe_key(article)
            if key in seen:
                continue
            seen.add(key)
            merged.append(article)
            if len(merged) >= MAX_RSS_ARTICLES:
                break
        if len(merged) >= MAX_RSS_ARTICLES:
            break

    if not merged and not notes:
        notes.append("RSS feeds returned no articles")
    return merged, notes
