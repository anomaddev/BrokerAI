from __future__ import annotations

import copy
from typing import Any


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        elif key == "filters" and isinstance(value, list):
            merged[key] = copy.deepcopy(value)
        elif key == "indicators" and isinstance(value, dict):
            merged_indicators = copy.deepcopy(merged.get("indicators", {}))
            for ind_id, ind_spec in value.items():
                if ind_id in merged_indicators and isinstance(ind_spec, dict):
                    merged_indicators[ind_id] = _deep_merge(merged_indicators[ind_id], ind_spec)
                else:
                    merged_indicators[ind_id] = copy.deepcopy(ind_spec)
            merged[key] = merged_indicators
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def merge_with_defaults(defaults: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    return _deep_merge(defaults, raw)
