from __future__ import annotations

import pytest

from brokerai.bots.researcher.rss import article_relevant_to_group, filter_articles_for_group
from brokerai.bots.researcher.rss_feeds import (
    DEFAULT_RSS_FEEDS,
    RSS_CATEGORIES,
    enabled_feeds,
    feeds_for_api,
    feeds_to_opml,
    normalize_rss_categories,
)
from brokerai.db.repositories.research_settings import _normalize_data_sources


def test_default_rss_catalog_has_expected_categories():
    assert set(RSS_CATEGORIES) == {
        "general",
        "finance",
        "finance_specialized",
        "geopolitics",
        "regional",
        "macro",
    }
    assert len(DEFAULT_RSS_FEEDS) >= 25
    assert all(feed["category"] in RSS_CATEGORIES for feed in DEFAULT_RSS_FEEDS)


def test_normalize_rss_categories_merges_unknown_keys():
    normalized = normalize_rss_categories({"finance": False, "unknown": True})
    assert normalized["finance"] is False
    assert normalized["general"] is True
    assert "unknown" not in normalized


def test_enabled_feeds_respects_category_toggles():
    categories = {category_id: category_id == "finance" for category_id in RSS_CATEGORIES}
    feeds = enabled_feeds(categories)
    assert feeds
    assert all(feed["category"] == "finance" for feed in feeds)
    assert "reuters-markets" in {feed["id"] for feed in feeds}


def test_feeds_for_api_includes_counts():
    payload = feeds_for_api({"macro": False})
    assert payload["total_feeds"] == len(DEFAULT_RSS_FEEDS)
    assert payload["enabled_feed_count"] < payload["total_feeds"]
    macro = next(item for item in payload["categories"] if item["id"] == "macro")
    assert macro["enabled"] is False


def test_feeds_to_opml_contains_enabled_urls():
    opml = feeds_to_opml({"finance": True, "general": False})
    assert "<opml" in opml
    assert "feeds.bloomberg.com/markets/news.rss" in opml
    assert "feeds.reuters.com/reuters/topNews" not in opml


def test_normalize_data_sources_includes_rss_defaults():
    sources = _normalize_data_sources(None)
    assert sources["rss_enabled"] is False
    assert sources["rss_categories"]["finance"] is True


def test_article_relevant_to_group_matches_currency_and_macro():
    article = {
        "title": "ECB keeps rates unchanged as euro steadies",
        "description": "Policy unchanged ahead of inflation data.",
        "url": "https://example.com/ecb",
        "source": "Reuters",
        "publishedAt": "2026-07-01T12:00:00+00:00",
    }
    assert article_relevant_to_group(article, "EUR", ["EUR/USD", "EUR/GBP"])

    macro_only = {
        "title": "FOMC minutes show split on rate path",
        "description": "Fed officials debated inflation risks.",
        "url": "https://example.com/fomc",
        "source": "Bloomberg",
        "publishedAt": "2026-07-01T12:00:00+00:00",
    }
    assert article_relevant_to_group(macro_only, "AUD", ["AUD/USD"])

    irrelevant = {
        "title": "Local sports team wins championship",
        "description": "Celebrations continue downtown.",
        "url": "https://example.com/sports",
        "source": "Local",
        "publishedAt": "2026-07-01T12:00:00+00:00",
    }
    assert not article_relevant_to_group(irrelevant, "USD", ["EUR/USD"])


def test_filter_articles_for_group_limits_results():
    articles = [
        {
            "title": "USD/JPY climbs after BoJ comments",
            "description": "Yen weakens on policy outlook.",
            "url": "https://example.com/usdjpy",
            "source": "Reuters",
            "publishedAt": "2026-07-02T12:00:00+00:00",
        },
        {
            "title": "Oil prices rise on supply concerns",
            "description": "Crude moves higher in Asia.",
            "url": "https://example.com/oil",
            "source": "Bloomberg",
            "publishedAt": "2026-07-01T12:00:00+00:00",
        },
        {
            "title": "Local weather update",
            "description": "Rain expected tomorrow.",
            "url": "https://example.com/weather",
            "source": "Local",
            "publishedAt": "2026-07-03T12:00:00+00:00",
        },
    ]
    filtered = filter_articles_for_group(articles, "USD", ["USD/JPY"], limit=1)
    assert len(filtered) == 1
    assert "USD/JPY" in filtered[0]["title"]
