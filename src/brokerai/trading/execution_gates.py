from __future__ import annotations

from typing import Any

from brokerai.trading.session_gate import is_asset_trading_session_active, is_strategy_session_active
from brokerai.trading.types import AnalysisResult, TradeIntent


def is_executor_eligible(result: AnalysisResult) -> bool:
    """Return whether broker should evaluate trade intents for this analysis.

    Zero-confidence or directionless runs still receive a persisted execution
    outcome (gate reasons only); they are never submitted to the associate.
    """
    return result.confidence > 0 and result.direction is not None


def passes_confidence_gate(result: AnalysisResult, params: dict[str, Any]) -> bool:
    execution = params.get("execution") or {}
    min_confidence = int(execution.get("min_confidence", 0))
    return result.confidence * 100 >= min_confidence


def passes_max_trades_gate(
    strategy_id: str,
    pair: str,
    params: dict[str, Any],
    trade_counts: dict[tuple[str, str], int],
) -> bool:
    risk = params.get("risk") or {}
    max_trades = int(risk.get("max_trades_per_day", 20))
    current = trade_counts.get((strategy_id, pair), 0)
    return current < max_trades


def passes_execution_gates(
    result: AnalysisResult,
    params: dict[str, Any],
    trade_counts: dict[tuple[str, str], int],
    *,
    when=None,
    asset_enabled_sessions: dict[str, bool] | None = None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if result.direction is None:
        reasons.append("no_signal")
    if not passes_confidence_gate(result, params):
        reasons.append("confidence_below_threshold")
    if asset_enabled_sessions is not None and not is_asset_trading_session_active(
        asset_enabled_sessions,
        when=when,
    ):
        reasons.append("asset_session_inactive")
    if not is_strategy_session_active(params, when=when):
        reasons.append("session_inactive")
    if not passes_max_trades_gate(result.strategy_id, result.pair, params, trade_counts):
        reasons.append("max_trades_reached")
    return len(reasons) == 0, reasons


def resolve_priority_conflicts(
    candidates: list[tuple[AnalysisResult, dict[str, Any]]],
) -> list[tuple[AnalysisResult, dict[str, Any]]]:
    """Pick winning analysis per pair when multiple strategies signal."""
    if not candidates:
        return []

    by_pair: dict[str, list[tuple[AnalysisResult, dict[str, Any]]]] = {}
    for result, params in candidates:
        by_pair.setdefault(result.pair, []).append((result, params))

    winners: list[tuple[AnalysisResult, dict[str, Any]]] = []
    for pair, entries in by_pair.items():
        _ = pair
        overrides = [
            entry
            for entry in entries
            if bool((entry[1].get("execution") or {}).get("override_all_strategies"))
        ]
        pool = overrides or entries
        pool.sort(key=lambda entry: int((entry[1].get("execution") or {}).get("priority", 50)))
        winners.append(pool[0])

    return winners
