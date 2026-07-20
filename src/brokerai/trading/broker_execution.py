from __future__ import annotations

import logging
import time

from brokerai.bots.associate.worker import AssociateWorker
from brokerai.bots.broker.gates import apply_execution_gates, record_execution_outcomes
from brokerai.bots.broker.monitor import BrokerMonitor
from brokerai.bots.data_manager.forex_strategies import load_runnable_forex_strategies
from brokerai.bots.data_manager.service import DataManagerService, require_data_manager_service
from brokerai.bots.secretary.types import PipelineContext
from brokerai.core.worker_pool import get_worker_pool
from brokerai.db.repositories.asset_settings import AssetSettingsRepository, enabled_forex_pairs
from brokerai.db.repositories.broker_lots import BrokerLotsRepository
from brokerai.trading.execution_gates import is_executor_eligible
from brokerai.trading.pipeline import ensure_trading_registries
from brokerai.trading.schedule import utc_now
from brokerai.trading.types import AnalysisResult, TradeIntent, WorkUnit

logger = logging.getLogger(__name__)


async def _strategies_by_id_for_context(context: PipelineContext) -> dict[str, dict]:
    """Build strategy lookup, always including strategies attached to the run context."""
    by_id: dict[str, dict] = {}
    loaded = await load_runnable_forex_strategies()
    for strategy, _pairs in loaded.strategies:
        strategy_id = str(strategy.get("id") or "")
        if strategy_id:
            by_id[strategy_id] = strategy
    for strategy in context.strategies:
        strategy_id = str(strategy.get("id") or "")
        if strategy_id:
            by_id[strategy_id] = strategy
    return by_id


async def run_broker_execution(
    results: list[AnalysisResult],
    context: PipelineContext,
    *,
    data_manager: DataManagerService | None = None,
) -> list[TradeIntent]:
    """Apply broker gates for analysis results and return trade intents to dispatch."""
    if not results:
        return []

    ensure_trading_registries()
    dm = data_manager or require_data_manager_service()
    strategies_by_id = await _strategies_by_id_for_context(context)
    trade_counts = await BrokerLotsRepository().daily_lot_counts()
    asset_settings = await AssetSettingsRepository().get(context.asset_class)
    only_one_position_per_pair = bool(asset_settings.get("only_one_position_per_pair", True))
    asset_enabled = bool(asset_settings.get("enabled"))
    asset_pairs = (
        enabled_forex_pairs(list(asset_settings.get("enabled_pairs") or []))
        if context.asset_class == "forex"
        else None
    )
    now = utc_now()

    ineligible = [analysis for analysis in results if not is_executor_eligible(analysis)]
    await record_execution_outcomes(
        ineligible,
        strategies_by_id,
        trade_counts=trade_counts,
        asset_enabled=asset_enabled,
        asset_enabled_pairs=asset_pairs,
        asset_enabled_sessions=asset_settings.get("enabled_sessions"),
        when=now,
        only_one_position_per_pair=only_one_position_per_pair,
    )

    actionable = [analysis for analysis in results if is_executor_eligible(analysis)]
    skipped = len(ineligible)

    unit = WorkUnit(
        pair=context.symbol,
        asset_class=context.asset_class,
        timeframe=context.timeframe,
        bar_count=context.bar_count,
        strategies=context.strategies,
    )
    monitor = BrokerMonitor()
    await monitor.sync_exit_monitors(
        [unit],
        dm,
        evaluate_pairs={(context.symbol, context.timeframe)},
    )

    # Re-query open pairs after exit monitors may have closed trades on this candle.
    open_lots = await BrokerLotsRepository().list_open_lots()
    open_pairs = {str(lot.get("pair")) for lot in open_lots if lot.get("pair")}

    if not actionable:
        logger.info(
            "Broker execution — no entry signal(s) for %s %s (%d result(s)); exit monitors evaluated",
            context.symbol,
            context.timeframe,
            len(results),
        )
        return []

    started = time.monotonic()
    intents = await apply_execution_gates(
        actionable,
        strategies_by_id,
        trade_counts=trade_counts,
        asset_enabled=asset_enabled,
        asset_enabled_pairs=asset_pairs,
        asset_enabled_sessions=asset_settings.get("enabled_sessions"),
        when=now,
        data_manager=dm,
        open_pairs=open_pairs,
        only_one_position_per_pair=only_one_position_per_pair,
    )

    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "Broker execution — %d result(s), %d skipped (no signal), %d intent(s) for %s %s in %dms",
        len(results),
        skipped,
        len(intents),
        context.symbol,
        context.timeframe,
        duration_ms,
    )
    return intents


async def dispatch_trade_intents(
    intents: list[TradeIntent],
    *,
    job_id: str | None = None,
) -> None:
    """Dispatch trade intents to associate workers."""
    if not intents:
        return

    pool = get_worker_pool()
    for intent in intents:
        result = await pool.run(AssociateWorker, intent, job_id=job_id)
        if not result.ok:
            logger.warning("Associate failed for %s: %s", intent.pair, result.error)
