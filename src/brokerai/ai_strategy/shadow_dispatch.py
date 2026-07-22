"""Shadow dispatch: record hypothetical intents/lots without Associate/OANDA."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from brokerai.ai_strategy.lifecycle import (
    PHASE_LIVE,
    get_execution_phase,
    is_ai_strategy_doc,
    is_catchup_context,
    is_shadow_phase,
)
from brokerai.db.repositories.shadow_trading import (
    ShadowIntentsRepository,
    ShadowLotsRepository,
    TradeOutcomeRecordsRepository,
)
from brokerai.trading.types import TradeIntent

logger = logging.getLogger(__name__)


def strategy_allows_live_dispatch(strategy: dict[str, Any] | None) -> bool:
    if not strategy:
        return True
    if not is_ai_strategy_doc(strategy):
        return True
    return get_execution_phase(strategy) == PHASE_LIVE


def filter_live_dispatch_intents(
    intents: list[TradeIntent],
    strategies_by_id: dict[str, dict],
) -> tuple[list[TradeIntent], list[TradeIntent]]:
    """Split intents into (live_dispatch, shadow_dispatch)."""
    live: list[TradeIntent] = []
    shadow: list[TradeIntent] = []
    for intent in intents:
        strategy = strategies_by_id.get(intent.strategy_id) or {}
        if strategy_allows_live_dispatch(strategy):
            live.append(intent)
        else:
            shadow.append(intent)
    return live, shadow


async def record_shadow_intents(
    intents: list[TradeIntent],
    *,
    strategies_by_id: dict[str, dict],
    context: Any = None,
) -> list[dict[str, Any]]:
    """Persist shadow intents/lots for warming/ready AI strategies. No-op on catchup."""
    if not intents:
        return []
    if is_catchup_context(context):
        logger.debug("Skipping shadow dispatch on catchup/bootstrap")
        return []

    intents_repo = ShadowIntentsRepository()
    lots_repo = ShadowLotsRepository()
    recorded: list[dict[str, Any]] = []
    for intent in intents:
        strategy = strategies_by_id.get(intent.strategy_id) or {}
        phase = get_execution_phase(strategy)
        if not is_shadow_phase(phase):
            continue
        meta = intent.metadata or {}
        entry_candle = str(meta.get("entry_candle_open") or meta.get("candle_time") or "")
        intent_doc = {
            "id": uuid4().hex,
            "strategy_id": intent.strategy_id,
            "strategy_name": intent.strategy_name,
            "pair": intent.pair,
            "timeframe": str(meta.get("timeframe") or ""),
            "phase": phase,
            "direction": intent.direction,
            "entry_price": intent.entry_price,
            "stop_loss": intent.stop_loss,
            "take_profit": intent.take_profit,
            "units": intent.units,
            "confidence": intent.confidence,
            "exit_mode": intent.exit_mode,
            "entry_candle_open": entry_candle,
            "analysis_run_id": meta.get("analysis_run_id"),
            "dispatch_mode": "shadow",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        saved = await intents_repo.upsert_intent(intent_doc)
        lot_doc = {
            "id": uuid4().hex,
            "strategy_id": intent.strategy_id,
            "pair": intent.pair,
            "timeframe": intent_doc["timeframe"],
            "state": "open",
            "direction": intent.direction,
            "entry_price": intent.entry_price,
            "stop_loss": intent.stop_loss,
            "take_profit": intent.take_profit,
            "units": abs(intent.units or 0) or 1000,
            "confidence": intent.confidence,
            "shadow_intent_id": saved["id"],
            "entry_candle_open": entry_candle,
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
        await lots_repo.upsert_lot(lot_doc)
        recorded.append(saved)
        logger.info(
            "Shadow intent recorded strategy=%s pair=%s direction=%s phase=%s",
            intent.strategy_id,
            intent.pair,
            intent.direction,
            phase,
        )
    return recorded


async def close_shadow_lot_with_outcome(
    lot: dict[str, Any],
    *,
    exit_price: float,
    exit_reason: str,
) -> dict[str, Any] | None:
    entry = float(lot.get("entry_price") or 0.0)
    units = float(lot.get("units") or 0.0)
    direction = str(lot.get("direction") or "long")
    if direction == "long":
        realized = (exit_price - entry) * units
    else:
        realized = (entry - exit_price) * units
    closed = await ShadowLotsRepository().close_lot(
        str(lot["id"]),
        exit_price=exit_price,
        exit_reason=exit_reason,
        realized_pnl=realized,
    )
    if closed is None:
        return None
    await TradeOutcomeRecordsRepository().append(
        {
            "strategy_id": lot["strategy_id"],
            "mode": "shadow",
            "pair": lot["pair"],
            "timeframe": lot.get("timeframe") or "",
            "direction": direction,
            "entry_ts": lot.get("opened_at"),
            "exit_ts": datetime.now(timezone.utc).isoformat(),
            "realized_pnl": realized,
            "close_reason": exit_reason,
            "entry_price": entry,
            "exit_price": exit_price,
            "shadow_lot_id": lot["id"],
            "hypothesis": lot.get("hypothesis"),
        }
    )
    return closed


def refuse_non_live_placement(strategy: dict[str, Any] | None) -> str | None:
    """Defense-in-depth: return error reason if placement must be refused."""
    if strategy is None:
        return None
    if not is_ai_strategy_doc(strategy):
        return None
    phase = get_execution_phase(strategy)
    if phase != PHASE_LIVE:
        return f"AI Strategy phase is {phase}; live placement refused"
    return None
