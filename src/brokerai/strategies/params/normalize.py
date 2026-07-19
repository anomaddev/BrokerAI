from __future__ import annotations

import copy
from typing import Any


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key == "filters" and isinstance(value, list):
            # Client sends the full filter list; do not union with defaults.
            merged[key] = copy.deepcopy(value)
        elif key == "indicators" and isinstance(value, dict):
            # Client sends the full indicator map (e.g. component ids). Replacing
            # avoids orphaning preset defaults like fast/slow beside ema_*.
            merged[key] = copy.deepcopy(value)
        elif key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def merge_with_defaults(defaults: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    return _deep_merge(defaults, raw)
