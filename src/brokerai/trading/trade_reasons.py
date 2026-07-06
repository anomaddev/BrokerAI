from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TradeReasonInfo:
    """Human-facing labels for a machine reason code."""

    label: str
    short: str
    category: str


# Short labels are capped at 19 characters for compact table display.
REASON_REGISTRY: dict[str, TradeReasonInfo] = {
    # Entry / execution
    "bullish_cross": TradeReasonInfo("Bullish Cross", "Bull cross", "signal"),
    "bearish_cross": TradeReasonInfo("Bearish Cross", "Bear cross", "signal"),
    "approaching_bullish_cross": TradeReasonInfo(
        "Approaching Bullish",
        "Approach Bull",
        "signal",
    ),
    "approaching_bearish_cross": TradeReasonInfo(
        "Approaching Bearish",
        "Approach Bear",
        "signal",
    ),
    "ema_crossover": TradeReasonInfo("EMA crossover", "EMA cross", "signal"),
    "oanda_import": TradeReasonInfo("Imported from OANDA", "OANDA import", "import"),
    "random_trade": TradeReasonInfo("Random Trade", "Random Trade", "other"),
    # Exit / close
    "reverse_crossover": TradeReasonInfo("Reverse crossover", "Rev crossover", "exit"),
    "trail_ema_slow": TradeReasonInfo("Trail stop (EMA slow)", "Trail EMA", "exit"),
    "trail_atr": TradeReasonInfo("Trail stop (ATR)", "Trail ATR", "exit"),
    "manual_close": TradeReasonInfo("Manual close", "Manual", "manual"),
    "broker_closed": TradeReasonInfo("Closed on OANDA", "Broker close", "broker"),
    "order_cancelled": TradeReasonInfo("Order cancelled", "Cancelled", "broker"),
    "ORDER_CANCELLED": TradeReasonInfo("Order cancelled", "Cancelled", "broker"),
    "STOP_LOSS_ON_FILL_LOSS": TradeReasonInfo(
        "Stop loss on fill rejected",
        "SL on fill",
        "broker",
    ),
    "STOP_LOSS_ON_FILL_PRICE_PRECISION_EXCEEDED": TradeReasonInfo(
        "Stop loss precision rejected",
        "SL precision",
        "broker",
    ),
}


def _fallback_short(label: str, *, max_len: int = 19) -> str:
    text = label.strip()
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1]}…"


def resolve_trade_reason(code: str | None) -> dict[str, Any]:
    """Resolve a reason code into label, short label, and category."""
    if not code or not str(code).strip():
        return {
            "code": None,
            "label": None,
            "short": None,
            "category": None,
        }

    normalized = str(code).strip()
    info = REASON_REGISTRY.get(normalized)
    if info is not None:
        return {
            "code": normalized,
            "label": info.label,
            "short": info.short,
            "category": info.category,
        }

    label = normalized.replace("_", " ").strip().title()
    return {
        "code": normalized,
        "label": label,
        "short": _fallback_short(label),
        "category": "other",
    }
