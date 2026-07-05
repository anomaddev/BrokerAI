from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from brokerai.bots.data_manager.candle_requirements import required_candle_bars, strategy_timeframe
from brokerai.bots.secretary.types import PipelineContext
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.db.repositories.strategy_analysis_runs import StrategyAnalysisRunsRepository
from brokerai.strategy_constants import WATCHLIST_ALL_SYMBOL

logger = logging.getLogger(__name__)

ANALYSIS_SUPPORTED_ASSET_CLASSES = frozenset({"forex", "metals"})

METALS_SYMBOL_CATALOG = ("XAU/USD", "XAG/USD", "XPT/USD", "XPD/USD")


def _normalize_symbol(asset_class: str, symbol: str) -> str:
    trimmed = symbol.strip()
    if not trimmed:
        raise ValueError("Symbol is required")
    if asset_class == "forex":
        from fastapi import HTTPException
        from brokerai.web.routes.market_data_helpers import resolve_forex_pair

        try:
            return resolve_forex_pair(trimmed)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "Invalid forex pair"
            raise ValueError(detail) from exc
    if asset_class == "metals":
        if trimmed in METALS_SYMBOL_CATALOG:
            return trimmed
        upper = trimmed.upper()
        for entry in METALS_SYMBOL_CATALOG:
            if entry.upper() == upper:
                return entry
        raise ValueError(f"Unknown metals symbol: {symbol}")
    return trimmed


def _strategy_covers_symbol(strategy: dict[str, Any], asset_class: str, symbol: str) -> bool:
    if str(strategy.get("asset_class") or "") == asset_class:
        instruments = strategy.get("instruments") or []
        if not instruments:
            return True
        normalized = symbol.upper()
        if any(str(item).upper() == normalized for item in instruments):
            return True

    selection = strategy.get("instrument_selection") or {}
    class_symbols = selection.get(asset_class)
    if not class_symbols:
        return False
    if len(class_symbols) == 1 and class_symbols[0] == WATCHLIST_ALL_SYMBOL:
        return True
    normalized = symbol.upper()
    return any(str(item).upper() == normalized for item in class_symbols if item != WATCHLIST_ALL_SYMBOL)


async def run_manual_strategy_analysis(
    *,
    strategy_id: str,
    asset_class: str,
    symbol: str,
) -> dict[str, Any]:
    """Run one strategy analysis for a single symbol and persist the result."""
    normalized_class = asset_class.strip().lower()
    if normalized_class not in ANALYSIS_SUPPORTED_ASSET_CLASSES:
        raise ValueError(
            f"Manual analysis is not yet supported for {asset_class}. "
            "Only forex and precious metals are available."
        )

    normalized_symbol = _normalize_symbol(normalized_class, symbol)

    strategy = await StrategiesRepository().get_by_id(strategy_id)
    if strategy is None:
        raise ValueError("Strategy not found")

    if not _strategy_covers_symbol(strategy, normalized_class, normalized_symbol):
        raise ValueError(
            f"Strategy is not assigned to {normalized_symbol} ({asset_class})"
        )

    timeframe = strategy_timeframe(strategy)
    if not timeframe:
        raise ValueError("Strategy has no timeframe configured")

    bar_count = required_candle_bars(strategy)
    now = datetime.now(timezone.utc)

    context = PipelineContext(
        job_id=str(uuid4()),
        asset_class=normalized_class,
        symbol=normalized_symbol,
        timeframe=timeframe,
        trigger_time=now,
        bar_count=bar_count,
        strategies=(strategy,),
        incremental=False,
        bootstrap=False,
    )

    logger.info(
        "Manual analysis — strategy=%s symbol=%s timeframe=%s",
        strategy.get("name") or strategy_id,
        normalized_symbol,
        timeframe,
    )

    from brokerai.bots.data_analyzer.assets import run_asset_analyst

    worker_result = await run_asset_analyst(context)
    if not worker_result.ok:
        raise RuntimeError(worker_result.error or "Analysis failed")

    analyses = worker_result.data or []
    if not analyses:
        metadata = worker_result.metadata or {}
        if metadata.get("skipped"):
            raise ValueError(
                f"Manual analysis is not yet supported for {asset_class}"
            )
        raise RuntimeError("Analysis produced no results")

    analysis = analyses[0]
    run_id = analysis.run_id
    if not run_id:
        raise RuntimeError("Analysis run was not persisted")

    repo = StrategyAnalysisRunsRepository()
    updated = await repo.set_run_type(run_id, "manual")
    if not updated:
        raise RuntimeError("Analysis run was not persisted")

    from brokerai.trading.broker_execution import dispatch_trade_intents, run_broker_execution

    intents = await run_broker_execution(analyses, context)
    await dispatch_trade_intents(intents, job_id=context.job_id)

    run = await repo.get_by_id(run_id)
    if run is None:
        raise RuntimeError("Analysis run was not persisted")
    return run
