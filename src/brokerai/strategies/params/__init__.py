from __future__ import annotations

from typing import Any

from brokerai.strategies.base import StrategyPreset
from brokerai.strategies.params.constants import SCHEMA_VERSION
from brokerai.strategies.params.legacy import is_legacy_flat_params, migrate_ema_crossover_flat
from brokerai.strategies.params.normalize import merge_with_defaults
from brokerai.strategies.params.sections import ParamsValidationError
from brokerai.strategies.params.validate import validate_params

__all__ = [
    "SCHEMA_VERSION",
    "ParamsValidationError",
    "prepare_params",
    "normalize_stored_params",
]


def _to_v1_raw(preset: StrategyPreset, raw: dict[str, Any]) -> dict[str, Any]:
    if not raw:
        return {}
    if raw.get("schema_version") == SCHEMA_VERSION:
        return raw
    if "indicators" in raw or "signal" in raw or "timeframe" in raw:
        return {**raw, "schema_version": SCHEMA_VERSION}
    if is_legacy_flat_params(raw):
        if preset.signal_type == "ema_crossover":
            return migrate_ema_crossover_flat(raw)
        raise ParamsValidationError("Legacy flat params require ema_crossover preset", field="params")
    raise ParamsValidationError(
        "params must be StrategyParams v1 (schema_version=1) or legacy flat EMA format",
        field="params",
    )


def prepare_params(preset: StrategyPreset, raw: dict[str, Any]) -> dict[str, Any]:
    """Migrate, merge defaults, validate, and return normalized v1 params."""
    v1_raw = _to_v1_raw(preset, raw)
    merged = merge_with_defaults(preset.default_params, v1_raw)
    return validate_params(preset, merged)


def normalize_stored_params(preset: StrategyPreset, stored: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize params read from MongoDB (includes legacy migration)."""
    if not stored:
        if preset.id == "custom":
            return dict(preset.default_params)
        return validate_params(preset, preset.default_params)
    return prepare_params(preset, stored)
