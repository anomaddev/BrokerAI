from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from brokerai.trading.types import AnalysisResult


def _coerce_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_dt(value: datetime | str | None) -> str | None:
    coerced = _coerce_utc(value)
    return coerced.isoformat() if coerced else None


def analysis_result_to_document(
    result: AnalysisResult,
    *,
    candle_time: datetime | str | None,
    run_id: str | None = None,
) -> dict[str, Any]:
    analyzed_at = _coerce_utc(result.analyzed_at) or datetime.now(timezone.utc)
    candle_dt = _coerce_utc(candle_time)
    return {
        "id": run_id or str(uuid4()),
        "strategy_id": result.strategy_id,
        "strategy_name": result.strategy_name,
        "pair": result.pair,
        "timeframe": result.timeframe,
        "direction": result.direction,
        "confidence": result.confidence,
        "signal_type": result.signal_type,
        "min_candles": result.min_candles,
        "metadata": dict(result.metadata),
        "candle_time": candle_dt,
        "analyzed_at": analyzed_at,
        "run_type": "live",
        "execution": None,
    }


def serialize_analysis_run(doc: dict[str, Any]) -> dict[str, Any]:
    execution = doc.get("execution")
    serialized_execution = None
    if isinstance(execution, dict):
        serialized_execution = dict(execution)
        if "processed_at" in serialized_execution:
            serialized_execution["processed_at"] = _format_dt(serialized_execution["processed_at"])

    return {
        "id": doc.get("id"),
        "strategy_id": doc.get("strategy_id"),
        "strategy_name": doc.get("strategy_name"),
        "pair": doc.get("pair"),
        "timeframe": doc.get("timeframe"),
        "direction": doc.get("direction"),
        "confidence": doc.get("confidence"),
        "signal_type": doc.get("signal_type"),
        "min_candles": doc.get("min_candles"),
        "metadata": doc.get("metadata") or {},
        "candle_time": _format_dt(doc.get("candle_time")),
        "analyzed_at": _format_dt(doc.get("analyzed_at")),
        "run_type": doc.get("run_type", "live"),
        "execution": serialized_execution,
    }
