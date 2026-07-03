from __future__ import annotations

import pytest

from brokerai.bots.researcher.sources import ResolvedSources, resolve_sources


def test_resolve_sources_includes_rss_settings():
    resolved = resolve_sources(
        data_sources={
            "newsapi": False,
            "rss_enabled": True,
            "rss_categories": {"finance": True, "general": False},
            "web_search_enabled": False,
            "x_search_enabled": False,
        },
        newsapi_doc={"enabled": True, "api_key": "secret"},
        capabilities_map={},
        models_by_id={},
    )
    assert resolved.rss_enabled is True
    assert resolved.rss_categories["finance"] is True
    assert resolved.rss_categories["general"] is False
    assert resolved.any_active is True
    assert "RSS" in resolved.describe()


def test_resolved_sources_any_active_without_newsapi_key():
    resolved = ResolvedSources(rss_enabled=True)
    assert resolved.any_active is True
