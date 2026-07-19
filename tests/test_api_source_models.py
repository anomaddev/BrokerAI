from __future__ import annotations

from brokerai.bots.researcher.llm import parse_model_catalog
from brokerai.bots.researcher.runner import (
    _needs_synthesis_llm,
    _resolve_contributors,
    _resolve_synthesis,
    _skip_per_model_daily_report,
)
from brokerai.db.repositories.ai_models import bind_source_model, source_model_name
from brokerai.db.repositories.research_settings import _normalize_contributor, _normalize_settings


def test_parse_model_catalog_openai_shape():
    models = parse_model_catalog(
        {
            "data": [
                {"id": "grok-4", "name": "Grok 4"},
                {"id": "grok-2"},
            ]
        }
    )
    assert [m["id"] for m in models] == ["grok-2", "grok-4"]
    assert models[1]["name"] == "Grok 4"


def test_parse_model_catalog_open_webui_list():
    models = parse_model_catalog(
        [
            {"id": "qwen2.5:7b", "name": "Qwen"},
            {"name": "llama3"},
        ]
    )
    assert [m["id"] for m in models] == ["llama3", "qwen2.5:7b"]


def test_parse_model_catalog_claude_shape():
    models = parse_model_catalog(
        {
            "data": [
                {"id": "claude-sonnet-4-20250514", "display_name": "Claude Sonnet 4"},
            ]
        }
    )
    assert models == [
        {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
    ]


def test_parse_model_catalog_filters_media_generation_models():
    models = parse_model_catalog(
        {
            "data": [
                {"id": "grok-4.3", "name": "Grok 4.3"},
                {"id": "grok-imagine-image"},
                {"id": "grok-imagine-video-1.5"},
                {"id": "dall-e-3"},
                {"id": "gpt-image-1"},
                {"id": "tts-1-hd"},
                {"id": "whisper-1"},
                {"id": "gpt-4o-audio-preview"},
                {"id": "gpt-4o"},
                {
                    "id": "media-only",
                    "output_modalities": ["image"],
                },
                {
                    "id": "priced-image",
                    "image_price": 2000,
                },
            ]
        }
    )
    assert [m["id"] for m in models] == ["gpt-4o", "grok-4.3"]


def test_bind_source_model_prefers_selection():
    source = {
        "id": "src1",
        "title": "Grok",
        "model_name": "grok-2",
        "default_model_name": "grok-3",
    }
    bound = bind_source_model(source, "grok-4")
    assert bound["model_name"] == "grok-4"
    assert source_model_name(source) == "grok-3"


def test_normalize_contributor_includes_model_name():
    entry = _normalize_contributor(
        {"model_id": "abc", "model_name": "grok-4", "enabled": True, "reasoning_effort": "high"}
    )
    assert entry == {
        "model_id": "abc",
        "model_name": "grok-4",
        "enabled": True,
        "reasoning_effort": "high",
    }


def test_normalize_settings_keeps_companion_model_names():
    doc = _normalize_settings(
        {
            "contributor_models": [
                {"model_id": "s1", "model_name": "grok-4", "enabled": True},
                {"model_id": "s1", "model_name": "grok-3", "enabled": True},
            ],
            "synthesis_model_id": "s1",
            "synthesis_model_name": "grok-4",
            "weekly_brief_model_id": "s1",
            "weekly_brief_model_name": "grok-3",
            "weekly_debrief_model_id": "s1",
            "weekly_debrief_model_name": "grok-2",
        }
    )
    assert len(doc["contributor_models"]) == 2
    assert doc["synthesis_model_name"] == "grok-4"
    assert doc["weekly_brief_model_name"] == "grok-3"
    assert doc["weekly_debrief_model_name"] == "grok-2"


def test_resolve_contributors_binds_selected_model_name():
    settings = {
        "contributor_models": [
            {
                "model_id": "src",
                "model_name": "grok-4",
                "enabled": True,
                "reasoning_effort": "high",
            }
        ]
    }
    models = {
        "src": {
            "id": "src",
            "title": "Grok",
            "enabled": True,
            "model_name": "grok-2",
            "default_model_name": "grok-2",
        }
    }
    resolved = _resolve_contributors(settings, models)
    assert len(resolved) == 1
    assert resolved[0][1]["model_name"] == "grok-4"


def test_same_source_different_models_need_synthesis():
    contributor = {
        "id": "src",
        "title": "Grok",
        "model_name": "grok-3",
    }
    synthesis = {
        "id": "src",
        "title": "Grok",
        "model_name": "grok-4",
    }
    assert _needs_synthesis_llm(
        contributor_reports=[{"model": "a", "content": "x"}],
        contributors=[({"model_id": "src"}, contributor)],
        synthesis_model=synthesis,
    )
    assert not _skip_per_model_daily_report(
        [({"model_id": "src"}, contributor)],
        synthesis,
    )


def test_resolve_synthesis_binds_name():
    settings = {"synthesis_model_id": "src", "synthesis_model_name": "grok-4"}
    models = {
        "src": {
            "id": "src",
            "title": "Grok",
            "enabled": True,
            "default_model_name": "grok-2",
        }
    }
    model, skip = _resolve_synthesis(settings, models, [])
    assert skip is None
    assert model is not None
    assert model["model_name"] == "grok-4"
