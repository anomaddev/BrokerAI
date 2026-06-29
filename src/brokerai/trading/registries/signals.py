from __future__ import annotations

from typing import Any, Protocol

from brokerai.strategies.evaluator import StrategyResult
from brokerai.trading.indicator_cache import IndicatorCacheView


class SignalEvaluator(Protocol):
    signal_type: str

    def evaluate(
        self,
        candles: list[dict[str, Any]],
        params: dict[str, Any],
        indicators: IndicatorCacheView,
    ) -> StrategyResult: ...


_SIGNALS: dict[str, SignalEvaluator] = {}


def register_signal(signal_type: str, evaluator: SignalEvaluator) -> None:
    _SIGNALS[signal_type] = evaluator


def get_signal_evaluator(signal_type: str) -> SignalEvaluator | None:
    return _SIGNALS.get(signal_type)


def list_signal_types() -> list[str]:
    return sorted(_SIGNALS)
