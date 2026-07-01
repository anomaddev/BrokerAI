from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from brokerai.bots.data_manager.candle_requirements import strategy_params
from brokerai.strategies.candles import effective_min_candles
from brokerai.trading.indicator_cache import IndicatorCache, IndicatorCacheView
from brokerai.trading.registries.filters import run_filter_chain
from brokerai.trading.registries.signals import get_signal_evaluator
from brokerai.trading.types import AnalysisResult

logger = logging.getLogger(__name__)

_REGISTERED = False


def ensure_trading_registries() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    from brokerai.trading.presets.ema_crossover import register_ema_crossover

    register_ema_crossover()
    _REGISTERED = True


def format_analysis_log(result: AnalysisResult) -> str:
    filters = result.metadata.get("filters", {})
    filter_bits = []
    if isinstance(filters, dict):
        for filter_id, detail in filters.items():
            if isinstance(detail, dict):
                status = "pass" if detail.get("passed") else "fail"
                filter_bits.append(f"{filter_id}:{status}")
    filter_label = ",".join(filter_bits) if filter_bits else "none"
    signal = result.metadata.get("signal", "none")
    direction = result.direction or "none"
    return (
        f"AnalysisResult strategy={result.strategy_name} ({result.strategy_id[:8]}…) "
        f"pair={result.pair} tf={result.timeframe} direction={direction} "
        f"confidence={result.confidence:.2f} filters={filter_label} "
        f"signal={signal} min_candles={result.min_candles}"
    )


def run_strategy_analysis(
    strategy: dict[str, Any],
    pair: str,
    candles: list[dict[str, Any]],
    indicators: IndicatorCacheView,
    *,
    timeframe: str | None = None,
) -> AnalysisResult:
    ensure_trading_registries()
    params = strategy_params(strategy)
    signal = params.get("signal") or {}
    signal_type = str(signal.get("type", ""))
    evaluator = get_signal_evaluator(signal_type)

    strategy_id = str(strategy.get("id", ""))
    strategy_name = str(strategy.get("name") or strategy_id)
    tf = timeframe or str(strategy.get("timeframe") or params.get("timeframe") or "")
    min_required = effective_min_candles(params)

    if evaluator is None:
        return AnalysisResult(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            pair=pair,
            timeframe=tf,
            confidence=0.0,
            direction=None,
            min_candles=min_required,
            signal_type=signal_type,
            metadata={"error": "unknown_signal_type"},
            analyzed_at=datetime.now(timezone.utc),
        )

    if len(candles) < min_required:
        return AnalysisResult(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            pair=pair,
            timeframe=tf,
            confidence=0.0,
            direction=None,
            min_candles=min_required,
            signal_type=signal_type,
            metadata={
                "reason": "insufficient_candles",
                "have": len(candles),
                "need": min_required,
            },
            analyzed_at=datetime.now(timezone.utc),
        )

    signal_result = evaluator.evaluate(candles, params, indicators)
    filters_passed, filter_metadata = run_filter_chain(
        list(params.get("filters") or []),
        candles,
        indicators,
        signal_result.direction,
    )

    confidence = signal_result.confidence if filters_passed else 0.0
    direction = signal_result.direction if filters_passed else None
    metadata = {**signal_result.metadata, "filters": filter_metadata, "filters_passed": filters_passed}

    return AnalysisResult(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        pair=pair,
        timeframe=tf,
        confidence=confidence,
        direction=direction,
        min_candles=signal_result.min_candles,
        signal_type=signal_type,
        metadata=metadata,
        analyzed_at=datetime.now(timezone.utc),
    )


def log_analysis_result(result: AnalysisResult) -> None:
    logger.info(format_analysis_log(result))
