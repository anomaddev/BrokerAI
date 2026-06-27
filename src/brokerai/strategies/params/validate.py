from __future__ import annotations

from typing import Any

from brokerai.strategies.base import StrategyPreset
from brokerai.strategies.params.sections import (
    ParamsValidationError,
    validate_execution,
    validate_exits,
    validate_filter,
    validate_indicator,
    validate_risk,
    validate_schema_version,
    validate_signal_ema_crossover,
    validate_timeframe,
)


def validate_params(preset: StrategyPreset, params: dict[str, Any]) -> dict[str, Any]:
    schema = preset.param_schema or {}
    indicators_schema = schema.get("indicators") or {}
    filters_schema = schema.get("filters") or {}

    version = validate_schema_version(params.get("schema_version"))
    timeframe = validate_timeframe(
        params.get("timeframe"),
        legacy_timeframes=params.get("timeframes"),
    )

    indicators_raw = params.get("indicators") or {}
    if not isinstance(indicators_raw, dict):
        raise ParamsValidationError("indicators must be an object", field="indicators")

    indicators: dict[str, Any] = {}
    for indicator_id, spec in indicators_raw.items():
        indicators[indicator_id] = validate_indicator(
            indicator_id,
            spec,
            schema=indicators_schema.get(indicator_id),
        )

    signal_type = preset.signal_type
    signal_raw = params.get("signal") or {}
    if signal_type == "ema_crossover":
        signal = validate_signal_ema_crossover(signal_raw, indicators, schema=schema.get("signal"))
    else:
        raise ParamsValidationError(f"Unsupported signal type: {signal_type}", field="signal.type")

    filters_raw = params.get("filters") or []
    if not isinstance(filters_raw, list):
        raise ParamsValidationError("filters must be an array", field="filters")

    filters_by_id = {item.get("id"): item for item in filters_schema if isinstance(item, dict) and item.get("id")}
    filters: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, spec in enumerate(filters_raw):
        normalized = validate_filter(
            index,
            spec,
            schema=filters_by_id.get(spec.get("id") if isinstance(spec, dict) else None),
        )
        if normalized["id"] in seen_ids:
            raise ParamsValidationError(
                f"Duplicate filter id: {normalized['id']}",
                field=f"filters[{index}].id",
            )
        seen_ids.add(normalized["id"])
        filters.append(normalized)

    exits = validate_exits(params.get("exits"), schema=schema.get("exits"))
    risk = validate_risk(params.get("risk"), schema=schema.get("risk"))
    execution = validate_execution(params.get("execution"), schema=schema.get("execution"))

    return {
        "schema_version": version,
        "timeframe": timeframe,
        "indicators": indicators,
        "signal": signal,
        "filters": filters,
        "exits": exits,
        "risk": risk,
        "execution": execution,
    }
