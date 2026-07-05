from __future__ import annotations

from brokerai.strategies.base import StrategyPreset
from brokerai.strategies.params.constants import SCHEMA_VERSION

DEFAULT_PARAMS: dict = {
    "schema_version": SCHEMA_VERSION,
    "timeframe": "M15",
    "indicators": {},
    "signal": {},
    "filters": [],
    "exits": {
        "stop_loss": {
            "mode": "atr_based",
            "atr_multiplier": 1.5,
            "fixed_pips": 15,
            "structure_lookback": 10,
        },
        "take_profit": {
            "mode": "rr_ratio",
            "risk_reward_ratio": 2.0,
            "fixed_pips": 30,
            "atr_multiplier": 2.5,
        },
    },
    "risk": {"risk_per_trade_pct": 1.0, "max_trades_per_day": 3},
    "execution": {
        "sessions": ["London", "NY"],
        "min_confidence": 60,
        "override_all_strategies": False,
        "priority": 50,
    },
}

PARAM_SCHEMA: dict = {
    "indicators": {},
    "filters": [],
    "signal": {},
    "exits": {},
    "risk": {
        "risk_per_trade_pct": {"minimum": 0.25, "maximum": 5.0},
        "max_trades_per_day": {"minimum": 1, "maximum": 20},
    },
    "execution": {
        "min_confidence": {"minimum": 0, "maximum": 100},
        "priority": {"minimum": 0, "maximum": 100},
    },
    "min_candles": {"maximum": 2000},
}

CUSTOM_PRESET = StrategyPreset(
    id="custom",
    name="Custom",
    description="Build a strategy from scratch by adding signals, filters, and rules.",
    asset_classes=["forex", "metals", "stocks", "crypto", "futures", "options"],
    route="/research/strategies/new/custom",
    signal_type="custom",
    default_params=DEFAULT_PARAMS,
    param_schema=PARAM_SCHEMA,
    locked=False,
)
