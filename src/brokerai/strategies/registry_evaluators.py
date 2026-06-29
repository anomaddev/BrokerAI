from __future__ import annotations

from brokerai.strategies.candles import effective_min_candles
from brokerai.strategies.evaluator import StrategyEvaluator, StrategyResult
from brokerai.trading.pipeline import ensure_trading_registries
from brokerai.trading.registries.signals import get_signal_evaluator


class _LegacyAdapter:
    def __init__(self, signal_type: str) -> None:
        self._signal_type = signal_type

    def evaluate(self, candles: list[dict], params: dict) -> StrategyResult:
        ensure_trading_registries()
        evaluator = get_signal_evaluator(self._signal_type)
        if evaluator is None:
            return StrategyResult(
                confidence=0.0,
                min_candles=effective_min_candles(params),
                direction=None,
                metadata={"signal_type": self._signal_type, "stub": True},
            )
        from brokerai.trading.indicator_cache import IndicatorCache

        cache = IndicatorCache().warm("", "", candles, [params])
        result = evaluator.evaluate(candles, params, cache)
        return result


def get_evaluator(signal_type: str) -> StrategyEvaluator | None:
    ensure_trading_registries()
    if get_signal_evaluator(signal_type) is None:
        return None
    return _LegacyAdapter(signal_type)
