"""AI Strategy signal registration (ModelSignalRuntime)."""

from __future__ import annotations

from brokerai.trading.presets.ai_strategy.runtime import (
    AiStrategySignalEvaluator,
    ModelSignalRuntime,
    clear_decision_cache,
    register_ai_strategy_signal,
)

__all__ = [
    "AiStrategySignalEvaluator",
    "ModelSignalRuntime",
    "clear_decision_cache",
    "register_ai_strategy",
    "register_ai_strategy_signal",
]


def register_ai_strategy() -> None:
    register_ai_strategy_signal()
