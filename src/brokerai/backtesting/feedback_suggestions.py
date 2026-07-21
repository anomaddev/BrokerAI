"""Structured AI feedback suggestions: allowlist, parse, validate, and patch.

Only paths that map to UI-visible strategy builder controls may appear in
suggestions. Invalid or unknown paths are dropped (never fail the whole job).
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

# Paths the EMA builder exposes (or will expose in the same change set).
# Filters use logical ids (atr/adx), not array indexes.
SUGGESTION_ALLOWLIST: frozenset[str] = frozenset(
    {
        "filters.atr.min_value",
        "filters.atr.min_value_jpy",
        "filters.atr.enabled",
        "filters.adx.threshold",
        "filters.adx.enabled",
        "risk.max_trades_per_day",
        "exits.stop_loss.atr_multiplier",
        "exits.stop_loss.mode",
        "exits.stop_loss.structure_lookback",
        "exits.reverse_crossover.min_bars_after_entry",
        "exits.reverse_crossover.min_confirmation_bars",
        "exits.reverse_crossover.min_separation_atr",
        "signal.approaching.enabled",
        "signal.approaching.max_gap_atr",
        "signal.approaching.min_narrow_bars",
        "execution.sessions",
        "execution.min_confidence",
        "execution.post_stop_cooldown_bars",
        "signal.direction",
        "filters.htf_bias.enabled",
        "filters.htf_bias.timeframe",
    }
)

# Soft bounds for suggestion validation (UI-aligned). Stricter schema may apply on save.
_PATH_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "filters.atr.min_value": (0.0001, 0.5),
    "filters.atr.min_value_jpy": (0.0001, 0.5),
    "filters.adx.threshold": (15.0, 40.0),
    "risk.max_trades_per_day": (1.0, 20.0),
    "exits.stop_loss.atr_multiplier": (0.5, 4.0),
    "exits.stop_loss.structure_lookback": (3.0, 50.0),
    "exits.reverse_crossover.min_bars_after_entry": (0.0, 30.0),
    "exits.reverse_crossover.min_confirmation_bars": (1.0, 5.0),
    "exits.reverse_crossover.min_separation_atr": (0.0, 1.0),
    "signal.approaching.max_gap_atr": (0.01, 5.0),
    "signal.approaching.min_narrow_bars": (1.0, 10.0),
    "execution.min_confidence": (0.0, 100.0),
    "execution.post_stop_cooldown_bars": (0.0, 30.0),
}

_STOP_LOSS_MODES = frozenset({"fixed_pips", "atr_based", "structure"})
_DIRECTIONS = frozenset({"long", "short", "both"})
_HTF_TIMEFRAMES = frozenset({"H1", "H4"})

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{[\s\S]*?\})\s*```",
    re.IGNORECASE,
)

SUGGESTION_PATH_LABELS: dict[str, str] = {
    "filters.atr.min_value": "Min ATR value",
    "filters.atr.min_value_jpy": "Min ATR — JPY pairs",
    "filters.atr.enabled": "ATR filter enabled",
    "filters.adx.threshold": "ADX threshold",
    "filters.adx.enabled": "ADX filter enabled",
    "risk.max_trades_per_day": "Max trades per day",
    "exits.stop_loss.atr_multiplier": "Stop-loss ATR multiplier",
    "exits.stop_loss.mode": "Stop-loss mode",
    "exits.stop_loss.structure_lookback": "Structure lookback",
    "exits.reverse_crossover.min_bars_after_entry": "RC min bars after entry",
    "exits.reverse_crossover.min_confirmation_bars": "RC confirmation bars",
    "exits.reverse_crossover.min_separation_atr": "RC min separation (× ATR)",
    "signal.approaching.enabled": "Approaching entries",
    "signal.approaching.max_gap_atr": "Approaching max gap (× ATR)",
    "signal.approaching.min_narrow_bars": "Approaching min narrow bars",
    "execution.sessions": "Trading sessions",
    "execution.min_confidence": "Min confidence",
    "execution.post_stop_cooldown_bars": "Cooldown bars after stop-loss",
    "signal.direction": "Direction",
    "filters.htf_bias.enabled": "Higher-timeframe bias",
    "filters.htf_bias.timeframe": "HTF bias timeframe",
}


def suggestion_label(path: str) -> str:
    return SUGGESTION_PATH_LABELS.get(path, path)


def _get_by_path(params: dict[str, Any], path: str) -> Any:
    if path.startswith("filters."):
        parts = path.split(".")
        if len(parts) < 3:
            return None
        filter_id = parts[1]
        field = parts[2]
        if filter_id == "htf_bias":
            # Stored as a filter object with type htf_bias, or nested under filters list.
            for item in params.get("filters") or []:
                if isinstance(item, dict) and (
                    item.get("id") == "htf_bias" or item.get("type") == "htf_bias"
                ):
                    return item.get(field)
            return None
        for item in params.get("filters") or []:
            if not isinstance(item, dict):
                continue
            if item.get("id") == filter_id or item.get("type") == filter_id:
                return item.get(field)
        return None

    cur: Any = params
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _set_by_path(params: dict[str, Any], path: str, value: Any) -> None:
    if path.startswith("filters."):
        parts = path.split(".")
        if len(parts) < 3:
            return
        filter_id = parts[1]
        field = parts[2]
        filters = params.setdefault("filters", [])
        if not isinstance(filters, list):
            params["filters"] = []
            filters = params["filters"]
        target = None
        for item in filters:
            if isinstance(item, dict) and (
                item.get("id") == filter_id or item.get("type") == filter_id
            ):
                target = item
                break
        if target is None:
            if filter_id == "htf_bias":
                target = {"id": "htf_bias", "type": "htf_bias", "enabled": True, "timeframe": "H4"}
            elif filter_id == "atr":
                target = {
                    "id": "atr",
                    "type": "atr",
                    "enabled": True,
                    "period": 14,
                    "min_value": 0.0008,
                    "min_value_jpy": 0.05,
                }
            elif filter_id == "adx":
                target = {
                    "id": "adx",
                    "type": "adx",
                    "enabled": True,
                    "period": 14,
                    "threshold": 25,
                    "compare": "gte",
                }
            else:
                return
            filters.append(target)
        target[field] = value
        return

    parts = path.split(".")
    cur: Any = params
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _value_in_bounds(path: str, value: Any) -> bool:
    bounds = _PATH_BOUNDS.get(path)
    if bounds is None:
        return True
    try:
        num = float(value)
    except (TypeError, ValueError):
        return False
    lo, hi = bounds
    if lo is not None and num < lo:
        return False
    if hi is not None and num > hi:
        return False
    return True


def _normalize_suggestion_value(path: str, value: Any) -> Any | None:
    if path.endswith(".enabled") or path == "filters.htf_bias.enabled":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
            return value.strip().lower() == "true"
        return None
    if path == "exits.stop_loss.mode":
        mode = str(value).strip()
        return mode if mode in _STOP_LOSS_MODES else None
    if path == "signal.direction":
        direction = str(value).strip()
        return direction if direction in _DIRECTIONS else None
    if path == "filters.htf_bias.timeframe":
        tf = str(value).strip().upper()
        return tf if tf in _HTF_TIMEFRAMES else None
    if path == "execution.sessions":
        if not isinstance(value, list):
            return None
        sessions = [str(s).strip() for s in value if str(s).strip()]
        return sessions if sessions else None
    if path in {
        "risk.max_trades_per_day",
        "exits.stop_loss.structure_lookback",
        "exits.reverse_crossover.min_bars_after_entry",
        "exits.reverse_crossover.min_confirmation_bars",
        "signal.approaching.min_narrow_bars",
        "execution.min_confidence",
        "execution.post_stop_cooldown_bars",
    }:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if path in {
        "filters.atr.min_value",
        "filters.atr.min_value_jpy",
        "filters.adx.threshold",
        "exits.stop_loss.atr_multiplier",
        "exits.reverse_crossover.min_separation_atr",
        "signal.approaching.max_gap_atr",
    }:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return value


def normalize_suggestion(raw: Any, *, params_snapshot: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Normalize one suggestion dict; return None if invalid / not allowlisted."""
    if not isinstance(raw, dict):
        return None
    path = str(raw.get("path") or "").strip()
    if path not in SUGGESTION_ALLOWLIST:
        return None
    to_value = _normalize_suggestion_value(path, raw.get("to"))
    if to_value is None:
        return None
    if not _value_in_bounds(path, to_value):
        return None

    from_value = raw.get("from")
    if from_value is None and isinstance(params_snapshot, dict):
        from_value = _get_by_path(params_snapshot, path)
    else:
        normalized_from = _normalize_suggestion_value(path, from_value)
        from_value = normalized_from if normalized_from is not None else from_value

    try:
        priority = int(raw.get("priority", 99))
    except (TypeError, ValueError):
        priority = 99

    suggestion_id = str(raw.get("id") or path.replace(".", "_"))
    rationale = str(raw.get("rationale") or "").strip()
    test_alone = bool(raw.get("test_alone", True))

    return {
        "id": suggestion_id,
        "path": path,
        "label": suggestion_label(path),
        "from": from_value,
        "to": to_value,
        "rationale": rationale,
        "priority": priority,
        "test_alone": test_alone,
    }


def normalize_suggestions(
    raw: Any,
    *,
    params_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        normalized = normalize_suggestion(item, params_snapshot=params_snapshot)
        if normalized is None:
            continue
        if normalized["path"] in seen:
            continue
        seen.add(normalized["path"])
        out.append(normalized)
    out.sort(key=lambda s: (int(s.get("priority") or 99), str(s.get("path") or "")))
    return out


def parse_suggestions_from_markdown(
    markdown: str,
    *,
    params_snapshot: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Extract suggestions JSON from markdown; return cleaned markdown + suggestions.

    Looks for a fenced JSON block containing a top-level ``suggestions`` array.
    The JSON fence is stripped from the narrative markdown when found.
    """
    text = markdown or ""
    suggestions: list[dict[str, Any]] = []
    cleaned = text

    for match in _JSON_FENCE_RE.finditer(text):
        blob = match.group(1)
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict) or "suggestions" not in parsed:
            continue
        suggestions = normalize_suggestions(
            parsed.get("suggestions"),
            params_snapshot=params_snapshot,
        )
        cleaned = (text[: match.start()] + text[match.end() :]).strip()
        break

    return cleaned, suggestions


def apply_suggestions_to_params(
    params: dict[str, Any],
    suggestions: list[dict[str, Any]],
    *,
    selected_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Deep-copy params and apply selected suggestions (by id or all)."""
    result = copy.deepcopy(params)
    for suggestion in suggestions:
        if selected_ids is not None and suggestion.get("id") not in selected_ids:
            continue
        path = str(suggestion.get("path") or "")
        if path not in SUGGESTION_ALLOWLIST:
            continue
        _set_by_path(result, path, suggestion.get("to"))
    return result


# Paths exposed to the LLM prompt (human-readable list).
ALLOWLIST_FOR_PROMPT = sorted(SUGGESTION_ALLOWLIST)
