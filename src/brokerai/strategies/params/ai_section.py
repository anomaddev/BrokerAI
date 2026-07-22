"""Validate top-level ``params.ai`` section for AI Strategy."""

from __future__ import annotations

from typing import Any

from brokerai.strategies.params.sections import ParamsValidationError, _require_dict

LLM_MODES = frozenset({"off", "on_signal_change", "interval", "manual"})

DEFAULT_AI_SECTION: dict[str, Any] = {
    "model_id": None,
    "use_daily_report": True,
    "use_weekly_brief": True,
    "use_weekly_debrief": True,
    "llm_mode": "off",
    "min_llm_interval_minutes": 240,
    "max_llm_calls_per_day": 12,
    "max_llm_calls_per_symbol_per_day": 4,
    "max_context_bars": 64,
    # Default on so daily improve / memory loops work for newly created strategies.
    "learn_enabled": True,
}


def validate_ai_section(raw: Any) -> dict[str, Any]:
    """Whitelist and bound AI Strategy knobs. Unknown keys are dropped."""
    data = _require_dict(raw if raw is not None else {}, "ai")
    out = dict(DEFAULT_AI_SECTION)

    model_id = data.get("model_id", out["model_id"])
    if model_id is None or model_id == "":
        out["model_id"] = None
    else:
        out["model_id"] = str(model_id).strip() or None

    for flag in ("use_daily_report", "use_weekly_brief", "use_weekly_debrief", "learn_enabled"):
        if flag in data:
            out[flag] = bool(data.get(flag))

    mode = data.get("llm_mode", out["llm_mode"])
    if not isinstance(mode, str) or mode.strip() not in LLM_MODES:
        raise ParamsValidationError(
            f"ai.llm_mode must be one of {sorted(LLM_MODES)}",
            field="ai.llm_mode",
        )
    out["llm_mode"] = mode.strip()

    def _bound_int(key: str, minimum: int, maximum: int, default: int) -> int:
        value = data.get(key, default)
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ParamsValidationError(f"ai.{key} must be an integer", field=f"ai.{key}") from exc
        if parsed < minimum or parsed > maximum:
            raise ParamsValidationError(
                f"ai.{key} must be between {minimum} and {maximum}",
                field=f"ai.{key}",
            )
        return parsed

    out["min_llm_interval_minutes"] = _bound_int("min_llm_interval_minutes", 15, 10080, 240)
    out["max_llm_calls_per_day"] = _bound_int("max_llm_calls_per_day", 0, 500, 12)
    out["max_llm_calls_per_symbol_per_day"] = _bound_int(
        "max_llm_calls_per_symbol_per_day", 0, 100, 4
    )
    out["max_context_bars"] = _bound_int("max_context_bars", 16, 500, 64)
    return out


def validate_signal_ai_strategy(spec: Any) -> dict[str, Any]:
    field = "signal"
    data = _require_dict(spec, field)
    signal_type = data.get("type")
    if not isinstance(signal_type, str) or signal_type.strip() != "ai_strategy":
        raise ParamsValidationError(
            "Expected signal type ai_strategy",
            field=f"{field}.type",
        )
    mode = data.get("mode", "scaffold")
    if not isinstance(mode, str) or not mode.strip():
        mode = "scaffold"
    return {"type": "ai_strategy", "mode": mode.strip()}


def validate_signal_compiled_playbook(spec: Any) -> dict[str, Any]:
    """Validate a compiled-playbook signal block (daily AI Strategy backtests)."""
    field = "signal"
    data = _require_dict(spec, field)
    signal_type = data.get("type")
    if not isinstance(signal_type, str) or signal_type.strip() != "compiled_playbook":
        raise ParamsValidationError(
            "Expected signal type compiled_playbook",
            field=f"{field}.type",
        )
    bias = data.get("bias", data.get("default_bias", "flat"))
    if not isinstance(bias, str) or bias.strip() not in {"long", "short", "flat", "both"}:
        raise ParamsValidationError(
            "compiled_playbook bias must be long|short|flat|both",
            field=f"{field}.bias",
        )
    out = dict(data)
    out["type"] = "compiled_playbook"
    out["bias"] = bias.strip()
    out["default_bias"] = out["bias"]
    return out
