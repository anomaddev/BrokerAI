"""Instrument constraints for AI Strategies (one symbol, one owner)."""

from __future__ import annotations

from typing import Any

from brokerai.ai_strategy.lifecycle import is_ai_strategy_doc
from brokerai.strategy_constants import WATCHLIST_ALL_SYMBOL


def validate_ai_strategy_instrument_selection(
    instrument_selection: dict[str, list[str]],
) -> str:
    """Validate and return the single forex symbol for an AI Strategy.

    Edge cases:
    - Empty selection → ValueError
    - Non-forex asset classes → ValueError (forex-only in v1)
    - Watchlist-all or multiple symbols → ValueError (exactly one pair)
    """
    if set(instrument_selection.keys()) - {"forex"}:
        raise ValueError("AI Strategy is forex-only in v1")
    forex = instrument_selection.get("forex") or []
    symbols = sorted(
        {
            str(symbol).strip()
            for symbol in forex
            if symbol and str(symbol).strip() and str(symbol).strip() != WATCHLIST_ALL_SYMBOL
        }
    )
    if len(symbols) != 1:
        raise ValueError("AI Strategy must target exactly one instrument")
    return symbols[0]


def ai_strategy_owns_instrument(doc: dict[str, Any], symbol: str) -> bool:
    """Return True when *doc* is an AI Strategy that includes *symbol*."""
    if not is_ai_strategy_doc(doc):
        return False
    needle = (symbol or "").strip()
    if not needle:
        return False
    instruments = list(doc.get("instruments") or [])
    if needle in instruments:
        return True
    selection = doc.get("instrument_selection") or {}
    forex = selection.get("forex") if isinstance(selection, dict) else None
    if isinstance(forex, list):
        return any(str(item).strip() == needle for item in forex if item)
    return False


def conflict_message(owner_name: str, symbol: str) -> str:
    label = (owner_name or "").strip() or "another AI Strategy"
    return f"Instrument {symbol} already has an AI Strategy ({label})"


def default_ai_strategy_name(symbol: str) -> str:
    """Canonical create-time name: ``AI Strategy - {symbol}``."""
    pair = (symbol or "").strip()
    if not pair:
        return "AI Strategy"
    return f"AI Strategy - {pair}"


def resolve_ai_strategy_name(name: str | None, symbol: str) -> str:
    """Apply the default name when the caller left a blank or generic title."""
    expected = default_ai_strategy_name(symbol)
    stripped = (name or "").strip()
    if not stripped or stripped == "AI Strategy":
        return expected
    return stripped
