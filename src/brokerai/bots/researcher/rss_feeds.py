"""Default RSS feed catalog for financial and geopolitical research.

All feeds are public, free RSS endpoints grouped by category for settings UI
and selective enablement. IDs are stable so user toggles survive catalog updates.
"""

from __future__ import annotations

from typing import Any

RSS_CATEGORIES: dict[str, dict[str, str]] = {
    "general": {
        "label": "General / Top Headlines",
        "description": "Broad breaking news and world headlines.",
    },
    "finance": {
        "label": "Financial / Markets / Business",
        "description": "Markets, business, and macro market moves.",
    },
    "finance_specialized": {
        "label": "Specialized Finance",
        "description": "Crypto and forex-focused outlets.",
    },
    "geopolitics": {
        "label": "Geopolitical / World Affairs",
        "description": "International relations and global conflict.",
    },
    "regional": {
        "label": "Regional / High-Impact",
        "description": "Europe, Asia, and U.S. policy wires.",
    },
    "macro": {
        "label": "Macro / Policy / Think Tanks",
        "description": "Policy research and institutional analysis.",
    },
}

DEFAULT_RSS_CATEGORY_ENABLED: dict[str, bool] = {key: True for key in RSS_CATEGORIES}

DEFAULT_RSS_FEEDS: list[dict[str, str]] = [
    # General / Top Headlines
    {
        "id": "reuters-top-news",
        "title": "Reuters Top News",
        "url": "http://feeds.reuters.com/reuters/topNews",
        "category": "general",
    },
    {
        "id": "bbc-world",
        "title": "BBC World News",
        "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "category": "general",
    },
    {
        "id": "ap-top-headlines",
        "title": "AP Top Headlines",
        "url": "https://apnews.com/rss",
        "category": "general",
    },
    {
        "id": "nyt-homepage",
        "title": "The New York Times Top Stories",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "category": "general",
    },
    {
        "id": "guardian-world",
        "title": "The Guardian World",
        "url": "https://www.theguardian.com/world/rss",
        "category": "general",
    },
    # Financial / Markets / Business
    {
        "id": "reuters-business",
        "title": "Reuters Business",
        "url": "http://feeds.reuters.com/reuters/businessNews",
        "category": "finance",
    },
    {
        "id": "reuters-markets",
        "title": "Reuters Markets",
        "url": "http://feeds.reuters.com/reuters/marketsNews",
        "category": "finance",
    },
    {
        "id": "bloomberg-markets",
        "title": "Bloomberg Markets",
        "url": "https://feeds.bloomberg.com/markets/news.rss",
        "category": "finance",
    },
    {
        "id": "bloomberg-business",
        "title": "Bloomberg Business",
        "url": "https://feeds.bloomberg.com/business/news.rss",
        "category": "finance",
    },
    {
        "id": "bloomberg-economics",
        "title": "Bloomberg Economics",
        "url": "https://feeds.bloomberg.com/economics/news.rss",
        "category": "finance",
    },
    {
        "id": "cnbc-top-news",
        "title": "CNBC Top News / Markets",
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.xml",
        "category": "finance",
    },
    {
        "id": "ft-home",
        "title": "Financial Times",
        "url": "https://www.ft.com/rss/home",
        "category": "finance",
    },
    {
        "id": "ft-markets",
        "title": "Financial Times Markets",
        "url": "https://www.ft.com/rss/markets",
        "category": "finance",
    },
    {
        "id": "wsj-business",
        "title": "Wall Street Journal Business",
        "url": "https://feeds.wsj.com/wsj/xml/rss/3_7014.xml",
        "category": "finance",
    },
    {
        "id": "yahoo-finance-top",
        "title": "Yahoo Finance Top Stories",
        "url": "https://finance.yahoo.com/rss/topstories",
        "category": "finance",
    },
    {
        "id": "seeking-alpha",
        "title": "Seeking Alpha",
        "url": "https://seekingalpha.com/feed.xml",
        "category": "finance",
    },
    {
        "id": "zerohedge",
        "title": "ZeroHedge",
        "url": "https://www.zerohedge.com/fullrss2.xml",
        "category": "finance",
    },
    # Specialized Finance
    {
        "id": "coindesk",
        "title": "CoinDesk (Crypto)",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "category": "finance_specialized",
    },
    {
        "id": "fxstreet",
        "title": "FXStreet (Forex)",
        "url": "https://www.fxstreet.com/rss",
        "category": "finance_specialized",
    },
    # Geopolitical / International
    {
        "id": "reuters-world",
        "title": "Reuters World News",
        "url": "http://feeds.reuters.com/reuters/worldNews",
        "category": "geopolitics",
    },
    {
        "id": "al-jazeera",
        "title": "Al Jazeera",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "category": "geopolitics",
    },
    {
        "id": "nyt-world",
        "title": "The New York Times World",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "category": "geopolitics",
    },
    {
        "id": "foreign-affairs",
        "title": "Foreign Affairs",
        "url": "https://www.foreignaffairs.com/rss.xml",
        "category": "geopolitics",
    },
    {
        "id": "foreign-policy",
        "title": "Foreign Policy",
        "url": "https://foreignpolicy.com/feed/",
        "category": "geopolitics",
    },
    # Regional / High-Impact Areas
    {
        "id": "reuters-europe",
        "title": "Reuters Europe",
        "url": "http://feeds.reuters.com/reuters/europeNews",
        "category": "regional",
    },
    {
        "id": "reuters-asia",
        "title": "Reuters Asia",
        "url": "http://feeds.reuters.com/reuters/asiaNews",
        "category": "regional",
    },
    {
        "id": "nyt-politics",
        "title": "The New York Times Politics",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
        "category": "regional",
    },
    # Macro / Policy / Think Tanks
    {
        "id": "brookings",
        "title": "Brookings Institution",
        "url": "https://www.brookings.edu/feed/",
        "category": "macro",
    },
    {
        "id": "cfr",
        "title": "Council on Foreign Relations",
        "url": "https://www.cfr.org/rss",
        "category": "macro",
    },
]

_FEEDS_BY_ID = {feed["id"]: feed for feed in DEFAULT_RSS_FEEDS}


def normalize_rss_categories(raw: Any) -> dict[str, bool]:
    """Merge stored category toggles with the current catalog defaults."""
    raw = raw if isinstance(raw, dict) else {}
    normalized = dict(DEFAULT_RSS_CATEGORY_ENABLED)
    for key in RSS_CATEGORIES:
        if key in raw:
            normalized[key] = bool(raw[key])
    return normalized


def enabled_feeds(categories: dict[str, bool] | None = None) -> list[dict[str, str]]:
    """Return catalog feeds whose category is enabled."""
    active = normalize_rss_categories(categories)
    return [feed for feed in DEFAULT_RSS_FEEDS if active.get(feed["category"], False)]


def feeds_for_api(categories: dict[str, bool] | None = None) -> dict[str, Any]:
    """Payload for settings UI: categories, feeds, and counts."""
    active = normalize_rss_categories(categories)
    feeds = [
        {**feed, "category_enabled": active.get(feed["category"], False)}
        for feed in DEFAULT_RSS_FEEDS
    ]
    return {
        "categories": [
            {
                "id": category_id,
                "label": meta["label"],
                "description": meta["description"],
                "enabled": active.get(category_id, False),
                "feed_count": sum(1 for feed in DEFAULT_RSS_FEEDS if feed["category"] == category_id),
            }
            for category_id, meta in RSS_CATEGORIES.items()
        ],
        "feeds": feeds,
        "total_feeds": len(DEFAULT_RSS_FEEDS),
        "enabled_feed_count": sum(1 for feed in feeds if feed["category_enabled"]),
    }


def feeds_to_opml(categories: dict[str, bool] | None = None) -> str:
    """Render enabled feeds as an OPML 2.0 document."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        "  <head>",
        "    <title>BrokerAI RSS Feeds</title>",
        "  </head>",
        "  <body>",
    ]
    for category_id, meta in RSS_CATEGORIES.items():
        category_feeds = [
            feed for feed in enabled_feeds(categories) if feed["category"] == category_id
        ]
        if not category_feeds:
            continue
        lines.append(f'    <outline text="{meta["label"]}" title="{meta["label"]}">')
        for feed in category_feeds:
            lines.append(
                f'      <outline type="rss" text="{feed["title"]}" title="{feed["title"]}" '
                f'xmlUrl="{feed["url"]}" htmlUrl="{feed["url"]}" />'
            )
        lines.append("    </outline>")
    lines.extend(["  </body>", "</opml>"])
    return "\n".join(lines) + "\n"


def get_feed_by_id(feed_id: str) -> dict[str, str] | None:
    return _FEEDS_BY_ID.get(feed_id)
