"""Fail-closed AI Strategy signal evaluator (Slice 1 stub — never calls LLM)."""

from __future__ import annotations

from typing import Any

from brokerai.strategies.candles import effective_min_candles
from brokerai.strategies.evaluator import StrategyResult
from brokerai.trading.indicator_cache import IndicatorCacheView
from brokerai.trading.registries.signals import register_signal


class AiStrategySignalEvaluator:
    """Scaffold evaluator: no direction, zero confidence, never invokes the LLM."""

    signal_type = "ai_strategy"

    def evaluate(
        self,
        candles: list[dict[str, Any]],
        params: dict[str, Any],
        indicators: IndicatorCacheView,
    ) -> StrategyResult:
        _ = indicators
        min_required = effective_min_candles(params)
        ai = params.get("ai") if isinstance(params.get("ai"), dict) else {}
        signal = params.get("signal") if isinstance(params.get("signal"), dict) else {}
        return StrategyResult(
            confidence=0.0,
            min_candles=min_required,
            direction=None,
            metadata={
                "signal": "none",
                "scaffold": True,
                "stub": True,
                "llm_called": False,
                "llm_mode": str(ai.get("llm_mode") or "off"),
                "mode": str(signal.get("mode") or "scaffold"),
                "have_candles": len(candles),
            },
        )


def register_ai_strategy_signal() -> None:
    register_signal("ai_strategy", AiStrategySignalEvaluator())


def register_ai_strategy() -> None:
    register_ai_strategy_signal()
