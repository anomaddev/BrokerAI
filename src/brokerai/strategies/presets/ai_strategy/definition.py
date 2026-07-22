from __future__ import annotations

from brokerai.strategies.base import StrategyPreset
from brokerai.strategies.params.constants import SCHEMA_VERSION
from brokerai.strategies.params.ai_section import DEFAULT_AI_SECTION

DEFAULT_PARAMS: dict = {
    "schema_version": SCHEMA_VERSION,
    "timeframe": "M15",
    "indicators": {},
    "signal": {"type": "ai_strategy", "mode": "scaffold"},
    "filters": [],
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
        "dont_hold_between_sessions": True,
        "dont_hold_between_markets": True,
        "close_before_market_hours": 2,
        "no_late_market_trading": True,
        "late_market_hours": 2,
        "post_stop_cooldown_bars": 0,
    },
    "min_candles": 64,
    "ai": dict(DEFAULT_AI_SECTION),
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
        "close_before_market_hours": {"minimum": 1, "maximum": 24},
        "late_market_hours": {"minimum": 1, "maximum": 24},
        "post_stop_cooldown_bars": {"minimum": 0, "maximum": 30},
    },
    "min_candles": {"maximum": 2000},
    "ai": {},
}

AI_STRATEGY_PRESET = StrategyPreset(
    id="ai_strategy",
    name="AI Strategy",
    description=(
        "Model-derived strategy for a single forex pair. Created enabled: runs required "
        "reports and improve backtests, then learns in shadow until you promote it to live. "
        "Only one AI Strategy is allowed per instrument."
    ),
    asset_classes=["forex"],
    route="/research/strategies/new/ai-strategy",
    signal_type="ai_strategy",
    default_params=DEFAULT_PARAMS,
    param_schema=PARAM_SCHEMA,
    locked=True,
)
