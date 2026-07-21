"""Tests for structured AI feedback suggestions."""

from __future__ import annotations

from brokerai.backtesting.feedback_suggestions import (
    apply_suggestions_to_params,
    normalize_suggestions,
    parse_suggestions_from_markdown,
)


def test_parse_suggestions_from_markdown_strips_json_fence():
    markdown = """## Summary
Looks choppy.

```json
{
  "suggestions": [
    {
      "id": "atr_floor",
      "path": "filters.atr.min_value",
      "from": 0.0008,
      "to": 0.05,
      "rationale": "JPY ATR floor",
      "priority": 1,
      "test_alone": true
    },
    {
      "id": "bogus",
      "path": "indicators.fast.period",
      "to": 12
    }
  ]
}
```
"""
    cleaned, suggestions = parse_suggestions_from_markdown(markdown)
    assert "```json" not in cleaned
    assert "Looks choppy" in cleaned
    assert len(suggestions) == 1
    assert suggestions[0]["path"] == "filters.atr.min_value"
    assert suggestions[0]["to"] == 0.05
    assert suggestions[0]["label"] == "Min ATR value"


def test_normalize_suggestions_rejects_out_of_bounds():
    out = normalize_suggestions(
        [
            {"path": "filters.atr.min_value", "to": 9.0},
            {"path": "risk.max_trades_per_day", "to": 2},
        ]
    )
    assert len(out) == 1
    assert out[0]["path"] == "risk.max_trades_per_day"


def test_apply_suggestions_to_params_patches_filter_and_execution():
    params = {
        "filters": [
            {"id": "atr", "type": "atr", "enabled": True, "period": 14, "min_value": 0.0008},
        ],
        "execution": {"sessions": ["London"], "min_confidence": 60, "post_stop_cooldown_bars": 0},
        "signal": {"type": "ema_crossover", "approaching": {"enabled": True}},
    }
    suggestions = normalize_suggestions(
        [
            {"id": "a", "path": "filters.atr.min_value", "to": 0.05},
            {"id": "b", "path": "execution.post_stop_cooldown_bars", "to": 6},
            {"id": "c", "path": "signal.approaching.enabled", "to": False},
        ]
    )
    patched = apply_suggestions_to_params(params, suggestions)
    atr = next(f for f in patched["filters"] if f["id"] == "atr")
    assert atr["min_value"] == 0.05
    assert patched["execution"]["post_stop_cooldown_bars"] == 6
    assert patched["signal"]["approaching"]["enabled"] is False
    # Original unchanged
    assert params["filters"][0]["min_value"] == 0.0008
