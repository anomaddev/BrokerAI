from __future__ import annotations

from brokerai.strategies.candles import effective_min_candles
from brokerai.strategies.evaluator import StrategyEvaluator, StrategyResult


class _StubEvaluator:
    def __init__(self, signal_type: str) -> None:
        self._signal_type = signal_type

    def evaluate(self, candles: list[dict], params: dict) -> StrategyResult:
        return StrategyResult(
            confidence=0.0,
            min_candles=effective_min_candles(params),
            direction=None,
            metadata={"signal_type": self._signal_type, "stub": True},
        )


class EmaCrossoverEvaluatorStub(_StubEvaluator):
    def __init__(self) -> None:
        super().__init__("ema_crossover")


_EVALUATORS: dict[str, StrategyEvaluator] = {
    "ema_crossover": EmaCrossoverEvaluatorStub(),
    "monthly_high": _StubEvaluator("monthly_high"),
    "monthly_low": _StubEvaluator("monthly_low"),
}


def get_evaluator(signal_type: str) -> StrategyEvaluator | None:
    return _EVALUATORS.get(signal_type)
