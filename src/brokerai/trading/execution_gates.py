from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.trading.session_gate import is_strategy_session_active
from brokerai.trading.session_hold import (
    effective_session_ids,
    is_effective_session_coverage,
    should_block_late_market_entry,
)
from brokerai.trading.types import AnalysisResult, TradeIntent


def is_executor_eligible(result: AnalysisResult) -> bool:
    """Return whether broker should evaluate trade intents for this analysis.

    Analyses with a detected signal (direction + confidence) always enter the
    executor path so every gate can run and denial reasons are persisted.
    Approaching signals are watch-only and never eligible for execution.
    """
    signal = result.metadata.get("signal")
    if signal == "none" or (isinstance(signal, str) and "approach" in signal):
        return False
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


def passes_open_position_gate(
    pair: str,
    *,
    open_pairs: set[str] | frozenset[str] | None,
    only_one_position_per_pair: bool,
) -> bool:
    """Block a new entry when the pair already has an open position.

    Exit monitors run before entry gates, so a reverse-cross close on the same
    candle removes the pair from ``open_pairs`` and allows a fresh entry signal.
    """
    if not only_one_position_per_pair:
        return True
    if not open_pairs:
        return True
    return pair not in open_pairs


def _filter_gate_reasons(result: AnalysisResult) -> tuple[list[str], dict[str, Any]]:
    """Build gate reasons and metric details for failed strategy filters."""
    if result.metadata.get("filters_passed", True):
        return [], {}

    reasons: list[str] = []
    details: dict[str, Any] = {}
    filters = result.metadata.get("filters") or {}
    if not isinstance(filters, dict):
        return ["filters_failed"], {}

    for filter_id, raw in filters.items():
        if not isinstance(raw, dict) or raw.get("skipped"):
            continue
        if raw.get("passed", True):
            continue
        reason = f"filter_{filter_id}_failed"
        reasons.append(reason)
        details[reason] = {
            key: value for key, value in raw.items() if key not in {"passed", "skipped"}
        }

    if not reasons:
        reasons.append("filters_failed")
    return reasons, details


def passes_execution_gates(
    result: AnalysisResult,
    params: dict[str, Any],
    trade_counts: dict[tuple[str, str], int],
    *,
    when=None,
    asset_enabled: bool | None = None,
    asset_enabled_pairs: set[str] | frozenset[str] | list[str] | None = None,
    asset_enabled_sessions: dict[str, bool] | None = None,
    open_pairs: set[str] | frozenset[str] | None = None,
    only_one_position_per_pair: bool = False,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Evaluate all broker gates; return pass flag, reason codes, and metric details.

    Asset hierarchy (same pattern as sessions):
    - Global asset must be enabled (``asset_enabled``) when provided
    - Pair must be in globally enabled pairs (``asset_enabled_pairs``) when provided
    - Sessions use effective = global ∩ strategy (not independent OR layers)
    """
    reasons: list[str] = []
    details: dict[str, Any] = {}

    if result.direction is None:
        reasons.append("no_signal")

    filter_reasons, filter_details = _filter_gate_reasons(result)
    reasons.extend(filter_reasons)
    details.update(filter_details)

    execution_cfg = params.get("execution") or {}
    min_confidence = int(execution_cfg.get("min_confidence", 0))
    if not passes_confidence_gate(result, params):
        reasons.append("confidence_below_threshold")
        details["confidence_below_threshold"] = {
            "confidence_pct": round(result.confidence * 100, 2),
            "min_confidence_pct": min_confidence,
        }

    if asset_enabled is False:
        reasons.append("asset_disabled")
        details["asset_disabled"] = {"pair": result.pair}

    if asset_enabled_pairs is not None:
        enabled_set = (
            set(asset_enabled_pairs)
            if not isinstance(asset_enabled_pairs, (set, frozenset))
            else asset_enabled_pairs
        )
        if result.pair not in enabled_set:
            reasons.append("pair_not_enabled")
            details["pair_not_enabled"] = {
                "pair": result.pair,
                "enabled_pairs": sorted(enabled_set),
            }

    gate_when = when if when is not None else datetime.now(timezone.utc)
    if asset_enabled_sessions is not None:
        # True intersection: session must be on globally AND on the strategy.
        effective = effective_session_ids(asset_enabled_sessions, params)
        if not effective or not is_effective_session_coverage(gate_when, effective):
            reasons.append("session_inactive")
            sessions = execution_cfg.get("sessions")
            details["session_inactive"] = {
                "allowed_sessions": list(sessions) if isinstance(sessions, list) else sessions,
                "effective_sessions": sorted(effective),
                "asset_enabled_sessions": asset_enabled_sessions,
            }
    elif not is_strategy_session_active(params, when=gate_when):
        # No asset session map supplied (unit tests / offline) — strategy sessions only.
        reasons.append("session_inactive")
        sessions = execution_cfg.get("sessions")
        details["session_inactive"] = {
            "allowed_sessions": list(sessions) if isinstance(sessions, list) else sessions,
        }

    late_blocked, late_details = should_block_late_market_entry(
        params,
        when=gate_when,
        asset_enabled_sessions=asset_enabled_sessions,
    )
    if late_blocked:
        reasons.append("late_market_trading")
        details["late_market_trading"] = late_details

    risk = params.get("risk") or {}
    max_trades = int(risk.get("max_trades_per_day", 20))
    current_trades = trade_counts.get((result.strategy_id, result.pair), 0)
    if not passes_max_trades_gate(result.strategy_id, result.pair, params, trade_counts):
        reasons.append("max_trades_reached")
        details["max_trades_reached"] = {
            "count": current_trades,
            "max_trades_per_day": max_trades,
        }

    if not passes_open_position_gate(
        result.pair,
        open_pairs=open_pairs,
        only_one_position_per_pair=only_one_position_per_pair,
    ):
        reasons.append("open_position_exists")
        details["open_position_exists"] = {"pair": result.pair}

    return len(reasons) == 0, reasons, details


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
