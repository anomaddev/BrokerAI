from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class StrategyResult:
    confidence: float
    min_candles: int
    direction: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class StrategyEvaluator(Protocol):
    def evaluate(self, candles: list[dict[str, Any]], params: dict[str, Any]) -> StrategyResult: ...
