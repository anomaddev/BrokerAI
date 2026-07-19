from __future__ import annotations

from typing import Any

from brokerai.strategies.params.constants import (
    CONFIRMATIONS,
    DEFAULT_PRIORITY,
    DIRECTIONS,
    FILTER_COMPARE,
    FILTER_TYPES,
    INDICATOR_TYPES,
    MIN_CANDLES_MAX,
    PRICE_SOURCES,
    PRIORITY_MAX,
    PRIORITY_MIN,
    SCHEMA_VERSION,
    STOP_LOSS_MODES,
    TAKE_PROFIT_MODES,
    TIMEFRAMES,
    TRAIL_MODES,
)


class ParamsValidationError(ValueError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        self.field = field
        super().__init__(message)


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ParamsValidationError(f"{field} must be an object", field=field)
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ParamsValidationError(f"{field} must be an array", field=field)
    return value


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ParamsValidationError(f"{field} must be a non-empty string", field=field)
    return value.strip()


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ParamsValidationError(f"{field} must be a boolean", field=field)
    return value


def _require_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParamsValidationError(f"{field} must be a number", field=field)
    return float(value)


def _require_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ParamsValidationError(f"{field} must be an integer", field=field)
    return value


def _check_bounds(value: float, field: str, minimum: float | None, maximum: float | None) -> None:
    if minimum is not None and value < minimum:
        raise ParamsValidationError(f"{field} must be >= {minimum}", field=field)
    if maximum is not None and value > maximum:
        raise ParamsValidationError(f"{field} must be <= {maximum}", field=field)


def _bounds_from_schema(schema: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not schema:
        return None, None
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    return (
        float(minimum) if minimum is not None else None,
        float(maximum) if maximum is not None else None,
    )


def validate_indicator(
    indicator_id: str,
    spec: Any,
    *,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    field = f"indicators.{indicator_id}"
    data = _require_dict(spec, field)
    indicator_type = _require_str(data.get("type"), f"{field}.type")
    if indicator_type not in INDICATOR_TYPES:
        raise ParamsValidationError(f"Unknown indicator type: {indicator_type}", field=f"{field}.type")

    period = _require_int(data.get("period"), f"{field}.period")
    period_bounds = _bounds_from_schema((schema or {}).get("period"))
    _check_bounds(float(period), f"{field}.period", *period_bounds)

    source = data.get("source", "close")
    source = _require_str(source, f"{field}.source")
    if source not in PRICE_SOURCES:
        raise ParamsValidationError(f"Unknown price source: {source}", field=f"{field}.source")

    normalized: dict[str, Any] = {"type": indicator_type, "period": period, "source": source}
    if indicator_type == "rsi":
        overbought = data.get("overbought", 70)
        oversold = data.get("oversold", 30)
        normalized["overbought"] = _require_number(overbought, f"{field}.overbought")
        normalized["oversold"] = _require_number(oversold, f"{field}.oversold")

    # Optional chart display color (UI-only; ignored by the signal engine).
    color_raw = data.get("color")
    if color_raw is not None:
        color = _require_str(color_raw, f"{field}.color")
        if len(color) > 64:
            raise ParamsValidationError(f"{field}.color must be <= 64 characters", field=f"{field}.color")
        normalized["color"] = color

    return normalized


def validate_filter(
    index: int,
    spec: Any,
    *,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    field = f"filters[{index}]"
    data = _require_dict(spec, field)
    filter_id = _require_str(data.get("id"), f"{field}.id")
    filter_type = _require_str(data.get("type"), f"{field}.type")
    if filter_type not in FILTER_TYPES:
        raise ParamsValidationError(f"Unknown filter type: {filter_type}", field=f"{field}.type")

    enabled = _require_bool(data.get("enabled", True), f"{field}.enabled")
    normalized: dict[str, Any] = {"id": filter_id, "type": filter_type, "enabled": enabled}

    if filter_type == "adx":
        period = _require_int(data.get("period"), f"{field}.period")
        threshold = _require_number(data.get("threshold"), f"{field}.threshold")
        compare = _require_str(data.get("compare", "gte"), f"{field}.compare")
        if compare not in FILTER_COMPARE:
            raise ParamsValidationError(f"Invalid compare operator: {compare}", field=f"{field}.compare")
        period_bounds = _bounds_from_schema((schema or {}).get("period"))
        threshold_bounds = _bounds_from_schema((schema or {}).get("threshold"))
        _check_bounds(float(period), f"{field}.period", *period_bounds)
        _check_bounds(threshold, f"{field}.threshold", *threshold_bounds)
        normalized.update({"period": period, "threshold": threshold, "compare": compare})

    elif filter_type == "atr":
        period = _require_int(data.get("period"), f"{field}.period")
        period_bounds = _bounds_from_schema((schema or {}).get("period"))
        _check_bounds(float(period), f"{field}.period", *period_bounds)
        normalized["period"] = period
        if "min_value" in data and data["min_value"] is not None:
            min_value = _require_number(data["min_value"], f"{field}.min_value")
            min_bounds = _bounds_from_schema((schema or {}).get("min_value"))
            _check_bounds(min_value, f"{field}.min_value", *min_bounds)
            normalized["min_value"] = min_value
        if "max_value" in data and data["max_value"] is not None:
            max_value = _require_number(data["max_value"], f"{field}.max_value")
            normalized["max_value"] = max_value

    elif filter_type == "rsi":
        period = _require_int(data.get("period"), f"{field}.period")
        normalized["period"] = period
        if "min_value" in data and data["min_value"] is not None:
            normalized["min_value"] = _require_number(data["min_value"], f"{field}.min_value")
        if "max_value" in data and data["max_value"] is not None:
            normalized["max_value"] = _require_number(data["max_value"], f"{field}.max_value")

    elif filter_type == "custom":
        expression = _require_str(data.get("expression", ""), f"{field}.expression")
        normalized["expression"] = expression

    return normalized


def validate_additional_timeframes(value: Any, *, primary: str) -> list[str] | None:
    """Optional extra candle timeframes to fetch alongside the primary."""
    if value is None:
        return None
    raw = _require_list(value, "additional_timeframes")
    if not raw:
        return None

    seen: set[str] = set()
    ordered: list[str] = []
    for index, item in enumerate(raw):
        field = f"additional_timeframes[{index}]"
        tf = _require_str(item, field)
        if tf not in TIMEFRAMES:
            raise ParamsValidationError(f"Unknown timeframe: {tf}", field=field)
        if tf == primary:
            raise ParamsValidationError(
                "additional_timeframes must not include the primary timeframe",
                field=field,
            )
        if tf in seen:
            raise ParamsValidationError(f"Duplicate timeframe: {tf}", field=field)
        seen.add(tf)
        ordered.append(tf)
    return ordered


def validate_timeframe(value: Any) -> str:
    if value is not None and value != "":
        return _normalize_timeframe(value, field="timeframe")

    raise ParamsValidationError("Timeframe is required", field="timeframe")


def validate_exits(
    spec: Any,
    *,
    schema: dict[str, Any] | None = None,
    signal_type: str | None = None,
) -> dict[str, Any]:
    field = "exits"
    data = _require_dict(spec, field)
    schema = schema or {}

    stop_loss = _require_dict(data.get("stop_loss"), f"{field}.stop_loss")
    sl_mode = _require_str(stop_loss.get("mode"), f"{field}.stop_loss.mode")
    if sl_mode not in STOP_LOSS_MODES:
        raise ParamsValidationError(f"Unknown stop loss mode: {sl_mode}", field=f"{field}.stop_loss.mode")
    sl_normalized: dict[str, Any] = {
        "enabled": _require_bool(stop_loss.get("enabled", True), f"{field}.stop_loss.enabled"),
        "mode": sl_mode,
    }
    if "atr_multiplier" in stop_loss:
        sl_normalized["atr_multiplier"] = _require_number(
            stop_loss["atr_multiplier"], f"{field}.stop_loss.atr_multiplier"
        )
    if "fixed_pips" in stop_loss:
        sl_normalized["fixed_pips"] = _require_int(stop_loss["fixed_pips"], f"{field}.stop_loss.fixed_pips")
    if "structure_lookback" in stop_loss:
        sl_normalized["structure_lookback"] = _require_int(
            stop_loss["structure_lookback"], f"{field}.stop_loss.structure_lookback"
        )

    take_profit_raw = _require_dict(data.get("take_profit"), f"{field}.take_profit")
    if "trailing" in data:
        raise ParamsValidationError(
            "exits.trailing is no longer supported; use take_profit.mode=trailing_stop",
            field=f"{field}.trailing",
        )

    tp_mode = _require_str(take_profit_raw.get("mode"), f"{field}.take_profit.mode")
    if tp_mode not in TAKE_PROFIT_MODES:
        raise ParamsValidationError(f"Unknown take profit mode: {tp_mode}", field=f"{field}.take_profit.mode")

    if tp_mode == "reverse_crossover" and signal_type != "ema_crossover":
        raise ParamsValidationError(
            "reverse_crossover take profit requires ema_crossover signal",
            field=f"{field}.take_profit.mode",
        )

    tp_normalized: dict[str, Any] = {
        "enabled": _require_bool(take_profit_raw.get("enabled", True), f"{field}.take_profit.enabled"),
        "mode": tp_mode,
    }
    if tp_mode in {"fixed_pips", "rr_ratio", "atr_based"}:
        if "risk_reward_ratio" in take_profit_raw:
            tp_normalized["risk_reward_ratio"] = _require_number(
                take_profit_raw["risk_reward_ratio"], f"{field}.take_profit.risk_reward_ratio"
            )
        if "fixed_pips" in take_profit_raw:
            tp_normalized["fixed_pips"] = _require_int(
                take_profit_raw["fixed_pips"], f"{field}.take_profit.fixed_pips"
            )
        if "atr_multiplier" in take_profit_raw:
            tp_normalized["atr_multiplier"] = _require_number(
                take_profit_raw["atr_multiplier"], f"{field}.take_profit.atr_multiplier"
            )
    elif tp_mode == "trailing_stop":
        trail_mode = _require_str(take_profit_raw.get("trail_mode"), f"{field}.take_profit.trail_mode")
        if trail_mode not in TRAIL_MODES:
            raise ParamsValidationError(
                f"Unknown trail mode: {trail_mode}",
                field=f"{field}.take_profit.trail_mode",
            )
        if trail_mode == "ema_slow" and signal_type != "ema_crossover":
            raise ParamsValidationError(
                "ema_slow trailing stop requires ema_crossover signal",
                field=f"{field}.take_profit.trail_mode",
            )
        tp_normalized["trail_mode"] = trail_mode
        if trail_mode == "ema_slow":
            trail_ema_ref = _require_str(
                take_profit_raw.get("trail_ema_ref", "slow"),
                f"{field}.take_profit.trail_ema_ref",
            )
            tp_normalized["trail_ema_ref"] = trail_ema_ref
        else:
            tp_normalized["trail_atr_multiplier"] = _require_number(
                take_profit_raw.get("trail_atr_multiplier", 1.0),
                f"{field}.take_profit.trail_atr_multiplier",
            )

    _ = schema
    return {
        "stop_loss": sl_normalized,
        "take_profit": tp_normalized,
    }


def validate_risk(spec: Any, *, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    field = "risk"
    data = _require_dict(spec, field)
    schema = schema or {}

    risk_per_trade_pct = _require_number(data.get("risk_per_trade_pct"), f"{field}.risk_per_trade_pct")
    max_trades = _require_int(data.get("max_trades_per_day"), f"{field}.max_trades_per_day")
    pct_bounds = _bounds_from_schema(schema.get("risk_per_trade_pct"))
    trades_bounds = _bounds_from_schema(schema.get("max_trades_per_day"))
    _check_bounds(risk_per_trade_pct, f"{field}.risk_per_trade_pct", *pct_bounds)
    _check_bounds(float(max_trades), f"{field}.max_trades_per_day", *trades_bounds)

    return {"risk_per_trade_pct": risk_per_trade_pct, "max_trades_per_day": max_trades}


def validate_execution(spec: Any, *, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    field = "execution"
    data = _require_dict(spec, field)
    schema = schema or {}

    sessions_raw = _require_list(data.get("sessions"), f"{field}.sessions")
    sessions = sorted({_require_str(item, f"{field}.sessions[]") for item in sessions_raw})
    if not sessions:
        raise ParamsValidationError(f"{field}.sessions must contain at least one session", field=f"{field}.sessions")

    min_confidence = _require_int(data.get("min_confidence"), f"{field}.min_confidence")
    confidence_bounds = _bounds_from_schema(schema.get("min_confidence"))
    _check_bounds(float(min_confidence), f"{field}.min_confidence", *confidence_bounds)

    override_all_strategies = _require_bool(
        data.get("override_all_strategies", False),
        f"{field}.override_all_strategies",
    )

    priority = data.get("priority", DEFAULT_PRIORITY)
    priority = _require_int(priority, f"{field}.priority")
    _check_bounds(float(priority), f"{field}.priority", PRIORITY_MIN, PRIORITY_MAX)

    _ = schema
    return {
        "sessions": sessions,
        "min_confidence": min_confidence,
        "override_all_strategies": override_all_strategies,
        "priority": priority,
    }


def validate_min_candles(
    value: Any,
    *,
    params: dict[str, Any],
) -> int:
    from brokerai.strategies.candles import compute_required_candles

    computed = compute_required_candles(params)
    if computed > MIN_CANDLES_MAX:
        raise ParamsValidationError(
            f"Computed minimum candles ({computed}) exceeds maximum allowed ({MIN_CANDLES_MAX})",
            field="min_candles",
        )

    if value is None:
        return computed

    min_candles = _require_int(value, "min_candles")
    if min_candles < computed:
        raise ParamsValidationError(
            f"min_candles must be >= {computed} (computed warmup from indicators/filters)",
            field="min_candles",
        )
    if min_candles > MIN_CANDLES_MAX:
        raise ParamsValidationError(
            f"min_candles must be <= {MIN_CANDLES_MAX}",
            field="min_candles",
        )
    return min_candles


def validate_signal_monthly_limit(
    spec: Any,
    *,
    expected_type: str,
) -> dict[str, Any]:
    field = "signal"
    data = _require_dict(spec, field)
    signal_type = _require_str(data.get("type"), f"{field}.type")
    if signal_type != expected_type:
        raise ParamsValidationError(
            f"Expected signal type {expected_type}, got {signal_type}",
            field=f"{field}.type",
        )
    return {"type": expected_type}


def validate_signal_ema_crossover(
    spec: Any,
    indicators: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    field = "signal"
    data = _require_dict(spec, field)
    signal_type = _require_str(data.get("type"), f"{field}.type")
    if signal_type != "ema_crossover":
        raise ParamsValidationError(f"Expected signal type ema_crossover, got {signal_type}", field=f"{field}.type")

    fast_ref = _require_str(data.get("fast_ref"), f"{field}.fast_ref")
    slow_ref = _require_str(data.get("slow_ref"), f"{field}.slow_ref")
    if fast_ref not in indicators:
        raise ParamsValidationError(f"Unknown indicator ref: {fast_ref}", field=f"{field}.fast_ref")
    if slow_ref not in indicators:
        raise ParamsValidationError(f"Unknown indicator ref: {slow_ref}", field=f"{field}.slow_ref")
    if fast_ref == slow_ref:
        raise ParamsValidationError("fast_ref and slow_ref must differ", field=field)

    fast_period = indicators[fast_ref]["period"]
    slow_period = indicators[slow_ref]["period"]
    if fast_period == slow_period:
        raise ParamsValidationError(
            "fast indicator period must be less than slow indicator period",
            field=field,
        )
    # Auto-correct reversed assignments (lower period belongs on fast).
    if fast_period > slow_period:
        fast_ref, slow_ref = slow_ref, fast_ref

    direction = _require_str(data.get("direction"), f"{field}.direction")
    if direction not in DIRECTIONS:
        raise ParamsValidationError(f"Invalid direction: {direction}", field=f"{field}.direction")

    confirmation = _require_str(data.get("confirmation"), f"{field}.confirmation")
    if confirmation not in CONFIRMATIONS:
        raise ParamsValidationError(f"Invalid confirmation: {confirmation}", field=f"{field}.confirmation")

    approaching_raw = data.get("approaching")
    approaching: dict[str, Any] | None = None
    if approaching_raw is not None:
        approaching_data = _require_dict(approaching_raw, f"{field}.approaching")
        approaching = {
            "enabled": _require_bool(approaching_data.get("enabled", True), f"{field}.approaching.enabled"),
            "max_gap_atr": _require_number(
                approaching_data.get("max_gap_atr", 0.5),
                f"{field}.approaching.max_gap_atr",
            ),
            "min_narrow_bars": _require_int(
                approaching_data.get("min_narrow_bars", 2),
                f"{field}.approaching.min_narrow_bars",
            ),
        }
        _check_bounds(approaching["max_gap_atr"], f"{field}.approaching.max_gap_atr", 0.01, 5.0)
        _check_bounds(approaching["min_narrow_bars"], f"{field}.approaching.min_narrow_bars", 1, 10)

    _ = schema
    normalized: dict[str, Any] = {
        "type": signal_type,
        "fast_ref": fast_ref,
        "slow_ref": slow_ref,
        "direction": direction,
        "confirmation": confirmation,
    }
    if approaching is not None:
        normalized["approaching"] = approaching
    return normalized


def _normalize_timeframe(value: Any, *, field: str) -> str:
    timeframe = _require_str(value, field)
    if timeframe not in TIMEFRAMES:
        raise ParamsValidationError(f"Invalid timeframe: {timeframe}", field=field)
    return timeframe


def validate_schema_version(value: Any) -> int:
    version = _require_int(value, "schema_version")
    if version != SCHEMA_VERSION:
        raise ParamsValidationError(
            f"Unsupported schema_version: {version} (expected {SCHEMA_VERSION})",
            field="schema_version",
        )
    return version
