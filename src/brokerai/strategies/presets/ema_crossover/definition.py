from __future__ import annotations

from brokerai.strategies.base import StrategyPreset
from brokerai.strategies.params.constants import SCHEMA_VERSION

DEFAULT_PARAMS: dict = {
    "schema_version": SCHEMA_VERSION,
    "timeframe": "M15",
    "indicators": {
        "fast": {"type": "ema", "period": 9, "source": "close"},
        "slow": {"type": "ema", "period": 21, "source": "close"},
    },
    "signal": {
        "type": "ema_crossover",
        "fast_ref": "fast",
        "slow_ref": "slow",
        "direction": "both",
        "confirmation": "close",
        "approaching": {
            "enabled": True,
            "max_gap_atr": 0.5,
            "min_narrow_bars": 2,
        },
    },
    "filters": [
        {
            "id": "adx",
            "type": "adx",
            "enabled": True,
            "period": 14,
            "threshold": 25,
            "compare": "gte",
        },
        {
            "id": "atr",
            "type": "atr",
            "enabled": True,
            "period": 14,
            "min_value": 0.0008,
            "min_value_jpy": 0.05,
        },
    ],
    "exits": {
        "stop_loss": {
            "enabled": True,
            "mode": "atr_based",
            "atr_multiplier": 1.5,
            "fixed_pips": 15,
            "fixed_pips_jpy": 50,
            "structure_lookback": 10,
        },
        "take_profit": {
            "enabled": True,
            "mode": "reverse_crossover",
            "risk_reward_ratio": 2.0,
            "fixed_pips": 30,
            "atr_multiplier": 2.5,
        },
        "reverse_crossover": {
            "enabled": True,
            "min_bars_after_entry": 6,
            "min_confirmation_bars": 2,
            "min_separation_atr": 0.2,
        },
    },
    "risk": {"risk_per_trade_pct": 1.0, "max_trades_per_day": 3},
    "execution": {
        "sessions": ["London", "NY"],
        "min_confidence": 60,
        "override_all_strategies": False,
        "priority": 50,
        "dont_hold_between_sessions": True,
        "dont_hold_between_markets": True,
        "close_before_market_hours": 2,
        "no_late_market_trading": True,
        "late_market_hours": 2,
        "post_stop_cooldown_bars": 0,
    },
}

PARAM_SCHEMA: dict = {
    "indicators": {
        "fast": {"period": {"type": "integer", "minimum": 3, "maximum": 50}},
        "slow": {"period": {"type": "integer", "minimum": 10, "maximum": 200}},
    },
    "filters": [
        {"id": "adx", "period": {"minimum": 7, "maximum": 28}, "threshold": {"minimum": 15, "maximum": 40}},
        {"id": "atr", "period": {"minimum": 7, "maximum": 28}, "min_value": {"minimum": 0.0001, "maximum": 0.5}, "min_value_jpy": {"minimum": 0.0001, "maximum": 0.5}},
    ],
    "signal": {},
    "exits": {},
    "risk": {
        "risk_per_trade_pct": {"minimum": 0.25, "maximum": 5.0},
        "max_trades_per_day": {"minimum": 1, "maximum": 20},
    },
    "execution": {
        "min_confidence": {"minimum": 0, "maximum": 100},
        "priority": {"minimum": 0, "maximum": 100},
        "close_before_market_hours": {"minimum": 1, "maximum": 24},
        "late_market_hours": {"minimum": 1, "maximum": 24},
        "post_stop_cooldown_bars": {"minimum": 0, "maximum": 30},
    },
    "min_candles": {"maximum": 2000},
}

EMA_CROSSOVER_PRESET = StrategyPreset(
    id="ema_crossover",
    name="EMA Crossover",
    description="9/21 EMA crossover on M15 with ADX + ATR filters for any forex pair.",
    asset_classes=["forex"],
    route="/research/strategies/new/ema-crossover",
    signal_type="ema_crossover",
    default_params=DEFAULT_PARAMS,
    param_schema=PARAM_SCHEMA,
)

# Runtime modules live under brokerai.trading.presets.ema_crossover
