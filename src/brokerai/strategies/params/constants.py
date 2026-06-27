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
TAKE_PROFIT_MODES = frozenset({"fixed_pips", "rr_ratio", "atr_based"})

INDICATOR_TYPES = frozenset({"ema", "sma", "rsi"})
FILTER_TYPES = frozenset({"adx", "atr", "rsi", "custom"})
SIGNAL_TYPES = frozenset({"ema_crossover"})

PRICE_SOURCES = frozenset({"close", "open", "high", "low", "hl2", "hlc3", "ohlc4"})

SECTIONS = (
    "schema_version",
    "timeframe",
    "indicators",
    "signal",
    "filters",
    "exits",
    "risk",
    "execution",
)
