from __future__ import annotations

SCHEMA_VERSION = 1

TIMEFRAMES = frozenset(
    {
        "M1",
        "M2",
        "M3",
        "M4",
        "M5",
        "M10",
        "M15",
        "M30",
        "H1",
        "H2",
        "H3",
        "H4",
        "H6",
        "H8",
        "H12",
        "D1",
        "W1",
        "MN",
    }
)
TIMEFRAME_ORDER = (
    "M1",
    "M2",
    "M3",
    "M4",
    "M5",
    "M10",
    "M15",
    "M30",
    "H1",
    "H2",
    "H3",
    "H4",
    "H6",
    "H8",
    "H12",
    "D1",
    "W1",
    "MN",
)
DIRECTIONS = frozenset({"long", "short", "both"})
CONFIRMATIONS = frozenset({"close", "pullback", "aggressive"})
FILTER_COMPARE = frozenset({"gte", "lte", "gt", "lt", "eq"})

STOP_LOSS_MODES = frozenset({"fixed_pips", "atr_based", "structure"})
TAKE_PROFIT_MODES = frozenset(
    {"fixed_pips", "rr_ratio", "atr_based", "reverse_crossover", "trailing_stop"}
)
TRAIL_MODES = frozenset({"ema_slow", "atr"})

MIN_CANDLES_MAX = 2000
PRIORITY_MIN = 0
PRIORITY_MAX = 100
DEFAULT_PRIORITY = 50
MARKET_HOURS_MIN = 1
MARKET_HOURS_MAX = 24
DEFAULT_CLOSE_BEFORE_MARKET_HOURS = 2
DEFAULT_LATE_MARKET_HOURS = 2

INDICATOR_TYPES = frozenset({"ema", "sma", "rsi"})
FILTER_TYPES = frozenset({"adx", "atr", "rsi", "custom", "htf_bias"})
SIGNAL_TYPES = frozenset({"ema_crossover", "monthly_high", "monthly_low", "ai_strategy"})

PRICE_SOURCES = frozenset({"close", "open", "high", "low", "hl2", "hlc3", "ohlc4"})

SECTIONS = (
    "schema_version",
    "timeframe",
    "additional_timeframes",
    "indicators",
    "signal",
    "filters",
    "exits",
    "risk",
    "execution",
    "min_candles",
    "ai",
)
