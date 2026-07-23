from __future__ import annotations

from typing import Any

from brokerai.strategies.base import StrategyPreset
from brokerai.strategies.params.ai_section import (
    validate_ai_section,
    validate_signal_ai_strategy,
    validate_signal_compiled_playbook,
)
from brokerai.strategies.params.sections import (
    ParamsValidationError,
    validate_additional_timeframes,
    validate_execution,
    validate_exits,
    validate_filter,
    validate_indicator,
    validate_min_candles,
    validate_risk,
    validate_schema_version,
    validate_signal_ema_crossover,
    validate_signal_monthly_limit,
    validate_timeframe,
)


def _resolve_signal_type(preset: StrategyPreset, signal_raw: dict[str, Any]) -> str:
    if preset.id == "custom":
        signal_type = signal_raw.get("type")
        if not isinstance(signal_type, str) or not signal_type.strip():
            raise ParamsValidationError("Signal type is required for custom strategies", field="signal.type")
        return signal_type.strip()
    return preset.signal_type


def _validate_signal(
    preset: StrategyPreset,
    signal_raw: dict[str, Any],
    indicators: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    signal_type = _resolve_signal_type(preset, signal_raw)
    if signal_type == "ema_crossover":
        return validate_signal_ema_crossover(signal_raw, indicators, schema=schema)
    if signal_type == "monthly_high":
        return validate_signal_monthly_limit(signal_raw, expected_type="monthly_high")
    if signal_type == "monthly_low":
        return validate_signal_monthly_limit(signal_raw, expected_type="monthly_low")
    if signal_type == "ai_strategy":
        return validate_signal_ai_strategy(signal_raw)
    if signal_type == "compiled_playbook":
        return validate_signal_compiled_playbook(signal_raw)
    raise ParamsValidationError(f"Unsupported signal type: {signal_type}", field="signal.type")


def validate_params(preset: StrategyPreset, params: dict[str, Any]) -> dict[str, Any]:
    schema = preset.param_schema or {}
    indicators_schema = schema.get("indicators") or {}
    filters_schema = schema.get("filters") or []

    version = validate_schema_version(params.get("schema_version"))
    timeframe = validate_timeframe(params.get("timeframe"))
    additional_timeframes = validate_additional_timeframes(
        params.get("additional_timeframes"),
        primary=timeframe,
    )

    indicators_raw = params.get("indicators") or {}
    if not isinstance(indicators_raw, dict):
        raise ParamsValidationError("indicators must be an object", field="indicators")

    signal_raw = params.get("signal") or {}
    if preset.id == "custom" and not signal_raw:
        raise ParamsValidationError("Custom strategies require a signal block", field="signal")

    signal_type_hint = signal_raw.get("type") if isinstance(signal_raw, dict) else None
    if preset.id == "custom" and signal_type_hint == "ema_crossover" and not indicators_raw:
        raise ParamsValidationError(
            "EMA crossover strategies require at least one indicator",
            field="indicators",
        )

    indicators: dict[str, Any] = {}
    for indicator_id, spec in indicators_raw.items():
        indicators[indicator_id] = validate_indicator(
            indicator_id,
            spec,
            schema=indicators_schema.get(indicator_id) if isinstance(indicators_schema, dict) else None,
        )

    signal = _validate_signal(preset, signal_raw, indicators, schema=schema.get("signal"))
    signal_type = signal["type"]

    filters_raw = params.get("filters") or []
    if not isinstance(filters_raw, list):
        raise ParamsValidationError("filters must be an array", field="filters")

    filters_by_id = {
        item.get("id"): item for item in filters_schema if isinstance(item, dict) and item.get("id")
    }
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

    partial: dict[str, Any] = {
        "schema_version": version,
        "timeframe": timeframe,
        "indicators": indicators,
        "signal": signal,
        "filters": filters,
    }
    if additional_timeframes is not None:
        partial["additional_timeframes"] = additional_timeframes

    exits = validate_exits(
        params.get("exits"),
        schema=schema.get("exits"),
        signal_type=signal_type,
    )
    # Keep trail EMA aligned with the (possibly auto-swapped) slow leg.
    take_profit = exits.get("take_profit") if isinstance(exits.get("take_profit"), dict) else None
    if (
        signal_type == "ema_crossover"
        and isinstance(take_profit, dict)
        and take_profit.get("trail_mode") == "ema_slow"
        and isinstance(signal.get("slow_ref"), str)
    ):
        exits = {
            **exits,
            "take_profit": {
                **take_profit,
                "trail_ema_ref": signal["slow_ref"],
            },
        }

    risk = validate_risk(params.get("risk"), schema=schema.get("risk"))
    execution = validate_execution(params.get("execution"), schema=schema.get("execution"))
    min_candles = validate_min_candles(params.get("min_candles"), params={**partial, "exits": exits})

    result: dict[str, Any] = {
        **partial,
        "min_candles": min_candles,
        "exits": exits,
        "risk": risk,
        "execution": execution,
    }
    # Persist top-level ``ai`` only when present or when the preset is AI Strategy
    # (otherwise unknown top-level keys remain dropped by design).
    if "ai" in params or preset.id == "ai_strategy" or signal_type == "ai_strategy":
        result["ai"] = validate_ai_section(params.get("ai"))
    return result
