from __future__ import annotations

from brokerai.config.settings import get_settings
from brokerai.trading.risk_intent import build_trade_intent
from brokerai.trading.types import AnalysisResult, TradeIntent


async def maybe_confirm_trade_intent(
    result: AnalysisResult,
    params: dict,
    candles: list[dict],
    *,
    asset_class: str = "forex",
) -> TradeIntent | None:
    """Optional AI confirmation gate before creating a trade intent."""
    settings = get_settings()
    intent = build_trade_intent(result, params, candles, asset_class=asset_class)
    if intent is None:
        return None

    if not settings.ai_confirmation_enabled:
        return intent

    # Placeholder for future LLM confirmation — currently passes through.
    intent.metadata["ai_confirmation"] = {"confirmed": True, "stub": True}
    return intent
