from __future__ import annotations

from typing import Any

from brokerai.strategies.params.constants import SCHEMA_VERSION

# Flat keys that indicate legacy (pre-v1) EMA crossover params.
_LEGACY_EMA_FLAT_KEYS = frozenset(
    {
        "fast_ema",
        "slow_ema",
        "adx_filter",
        "adx_period",
        "adx_threshold",
        "atr_filter",
        "atr_period",
        "min_atr",
        "stop_loss_type",
        "sl_atr_multiplier",
        "sl_fixed_pips",
        "sl_structure_lookback",
        "take_profit_type",
        "risk_reward_ratio",
        "tp_fixed_pips",
        "tp_atr_multiplier",
        "trailing_stop",
        "trail_atr_multiplier",
        "risk_per_trade",
    }
)


def is_legacy_flat_params(raw: dict[str, Any]) -> bool:
    if not raw:
        return False
    if raw.get("schema_version") == SCHEMA_VERSION:
        return False
    if "indicators" in raw or "signal" in raw:
        return False
    return bool(_LEGACY_EMA_FLAT_KEYS & set(raw.keys()))


def _legacy_timeframe(raw: dict[str, Any]) -> str:
    legacy = raw.get("timeframe")
    if isinstance(legacy, str) and legacy:
        return legacy
    timeframes = raw.get("timeframes")
    if isinstance(timeframes, list) and timeframes:
        first = timeframes[0]
        if isinstance(first, str) and first:
            return first
    return "M15"


def migrate_ema_crossover_flat(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy flat EMA crossover params to StrategyParams v1."""
    return {
        "schema_version": SCHEMA_VERSION,
        "timeframe": _legacy_timeframe(raw),
        "indicators": {
            "fast": {
                "type": "ema",
                "period": int(raw.get("fast_ema", 9)),
                "source": "close",
            },
            "slow": {
                "type": "ema",
                "period": int(raw.get("slow_ema", 21)),
                "source": "close",
            },
        },
        "signal": {
            "type": "ema_crossover",
            "fast_ref": "fast",
            "slow_ref": "slow",
            "direction": raw.get("direction", "both"),
            "confirmation": raw.get("confirmation", "close"),
        },
        "filters": [
            {
                "id": "adx",
                "type": "adx",
                "enabled": bool(raw.get("adx_filter", True)),
                "period": int(raw.get("adx_period", 14)),
                "threshold": float(raw.get("adx_threshold", 25)),
                "compare": "gte",
            },
            {
                "id": "atr",
                "type": "atr",
                "enabled": bool(raw.get("atr_filter", True)),
                "period": int(raw.get("atr_period", 14)),
                "min_value": float(raw.get("min_atr", 0.0008)),
            },
        ],
        "exits": {
            "stop_loss": {
                "mode": raw.get("stop_loss_type", "atr_based"),
                "atr_multiplier": float(raw.get("sl_atr_multiplier", 1.5)),
                "fixed_pips": int(raw.get("sl_fixed_pips", 15)),
                "structure_lookback": int(raw.get("sl_structure_lookback", 10)),
            },
            "take_profit": {
                "mode": raw.get("take_profit_type", "rr_ratio"),
                "risk_reward_ratio": float(raw.get("risk_reward_ratio", 2.0)),
                "fixed_pips": int(raw.get("tp_fixed_pips", 30)),
                "atr_multiplier": float(raw.get("tp_atr_multiplier", 2.5)),
            },
            "trailing": {
                "enabled": bool(raw.get("trailing_stop", False)),
                "atr_multiplier": float(raw.get("trail_atr_multiplier", 1.0)),
            },
        },
        "risk": {
            "risk_per_trade_pct": float(raw.get("risk_per_trade", 1.0)),
            "max_trades_per_day": int(raw.get("max_trades_per_day", 3)),
        },
        "execution": {
            "sessions": list(raw.get("sessions") or ["London", "NY"]),
            "min_confidence": int(raw.get("min_confidence", 60)),
            "override_all_strategies": bool(raw.get("override_all_strategies", False)),
        },
    }
