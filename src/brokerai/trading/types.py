from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WorkUnit:
    pair: str
    asset_class: str
    timeframe: str
    bar_count: int
    strategies: tuple[dict, ...]


@dataclass(frozen=True)
class WorkPlan:
    units: tuple[WorkUnit, ...]
    timeframes: tuple[str, ...]


@dataclass
class AnalysisResult:
    strategy_id: str
    strategy_name: str
    pair: str
    timeframe: str
    confidence: float
    direction: str | None
    min_candles: int
    signal_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    analyzed_at: datetime | None = None
    run_id: str | None = None


@dataclass
class TradeIntent:
    strategy_id: str
    strategy_name: str
    pair: str
    asset_class: str
    direction: str
    confidence: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    exit_mode: str
    risk_pct: float
    units: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExitIntent:
    trade_id: str
    strategy_id: str
    pair: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
