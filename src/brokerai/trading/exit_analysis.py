from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.db.repositories.strategy_analysis_runs import StrategyAnalysisRunsRepository
from brokerai.trading.analysis_runs import analysis_result_to_document
from brokerai.trading.schedule import utc_now
from brokerai.trading.types import AnalysisResult, ExitIntent


def trade_requires_exit_monitor(params: dict[str, Any]) -> bool:
    """Return True when strategy params use a runtime exit monitor (not fixed TP)."""
    exits = params.get("exits") or {}
    tp_mode = str((exits.get("take_profit") or {}).get("mode", ""))
    return tp_mode in {"reverse_crossover", "trailing_stop"}


def build_exit_analysis_result(
    trade: dict[str, Any],
    strategy: dict[str, Any],
    *,
    timeframe: str,
    exit_intent: ExitIntent | None,
    signal_metadata: dict[str, Any] | None = None,
    analyzed_at: datetime | None = None,
) -> AnalysisResult:
    """Build an analysis run representing exit-signal evaluation for an open trade."""
    strategy_id = str(trade.get("strategy_id") or strategy.get("id") or "")
    strategy_name = str(trade.get("strategy_name") or strategy.get("name") or strategy_id)
    pair = str(trade.get("pair") or "")
    trade_direction = str(trade.get("direction") or "long")
    trade_id = str(trade.get("id") or "")

    metadata: dict[str, Any] = {
        "analysis_purpose": "exit",
        "trade_id": trade_id,
        "trade_direction": trade_direction,
        "exit_mode": str(trade.get("exit_mode") or ""),
    }
    if signal_metadata:
        metadata.update(signal_metadata)

    if exit_intent is not None:
        metadata["exit_reason"] = exit_intent.reason
        metadata["exit_triggered"] = True
        if exit_intent.metadata:
            metadata.update(exit_intent.metadata)
        signal = metadata.get("signal")
        if isinstance(signal, str) and signal != "none":
            direction = "long" if "bullish" in signal else "short" if "bearish" in signal else None
        else:
            direction = "short" if trade_direction == "long" else "long"
        confidence = float(metadata.get("confidence", 0) or 0)
    else:
        metadata.setdefault("signal", "none")
        metadata["exit_triggered"] = False
        direction = None
        confidence = 0.0

    return AnalysisResult(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        pair=pair,
        timeframe=timeframe,
        confidence=confidence,
        direction=direction,
        min_candles=0,
        signal_type="exit_monitor",
        metadata=metadata,
        analyzed_at=analyzed_at or utc_now(),
    )


async def persist_exit_analysis(
    result: AnalysisResult,
    *,
    trade_id: str,
    candle_time: datetime | str | None,
    exit_closed: bool,
    exit_reason: str | None = None,
) -> dict[str, Any]:
    """Persist an exit analysis run and attach execution outcome metadata."""
    doc = analysis_result_to_document(
        result,
        candle_time=candle_time,
        analysis_purpose="exit",
        trade_id=trade_id,
    )
    processed_at = utc_now()
    doc["execution"] = {
        "processed_at": processed_at.isoformat(),
        "analysis_purpose": "exit",
        "exit_triggered": bool(result.metadata.get("exit_triggered")),
        "exit_closed": exit_closed,
        "exit_reason": exit_reason,
        "trade_id": trade_id,
        "gates_passed": bool(result.metadata.get("exit_triggered")),
        "gate_reasons": [] if result.metadata.get("exit_triggered") else ["no_exit_signal"],
        "gate_details": {},
        "priority_winner": True,
        "intent_queued": False,
        "intent": None,
    }
    repo = StrategyAnalysisRunsRepository()
    persisted = await repo.insert_from_document(doc)
    result.run_id = persisted["id"]
    return persisted


async def persist_exit_analysis_run(
    trade: dict[str, Any],
    strategy: dict[str, Any],
    *,
    timeframe: str,
    exit_intent: ExitIntent | None,
    signal_metadata: dict[str, Any] | None,
    candle_time: datetime | str | None,
    exit_closed: bool,
) -> dict[str, Any] | None:
    """Build and persist an exit analysis run for the analysis table."""
    trade_id = str(trade.get("id") or "")
    if not trade_id:
        return None
    result = build_exit_analysis_result(
        trade,
        strategy,
        timeframe=timeframe,
        exit_intent=exit_intent,
        signal_metadata=signal_metadata,
    )
    return await persist_exit_analysis(
        result,
        trade_id=trade_id,
        candle_time=candle_time,
        exit_closed=exit_closed,
        exit_reason=exit_intent.reason if exit_intent else None,
    )
