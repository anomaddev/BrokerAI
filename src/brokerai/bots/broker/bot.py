from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING

from brokerai.bots.associate.worker import AssociateWorker
from brokerai.bots.base import Bot
from brokerai.bots.broker.monitor import BrokerMonitor
from brokerai.bots.data_manager.forex_strategies import load_runnable_forex_strategies
from brokerai.bots.data_manager.service import DataManagerService, require_data_manager_service
from brokerai.bots.secretary.activity import (
    log_pipeline_associate_completed,
    log_pipeline_associate_started,
    log_pipeline_broker_completed,
    log_pipeline_broker_started,
)
from brokerai.bots.secretary.types import PipelineContext
from brokerai.core.worker_pool import get_worker_pool
from brokerai.trading.execution_gates import is_executor_eligible
from brokerai.trading.pipeline import ensure_trading_registries
from brokerai.trading.schedule import utc_now
from brokerai.trading.types import AnalysisResult, TradeIntent

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class BrokerBot(Bot):
    """Persistent execution authority: gates, exit monitors, associate dispatch."""

    name = "broker"

    def __init__(self) -> None:
        super().__init__()
        self._monitor = BrokerMonitor()
        self._strategies_by_id: dict[str, dict] = {}
        self._processed_analysis_at: dict[tuple[str, str], datetime | None] = {}
        self._last_sync_at: datetime | None = None
        self._data_manager: DataManagerService | None = None

    def attach_data_manager(self, service: DataManagerService) -> None:
        self._data_manager = service

    async def on_start(self) -> None:
        ensure_trading_registries()
        self._processed_analysis_at.clear()
        from brokerai.trading.broker.sync import run_broker_sync

        await run_broker_sync(exchange_id="oanda", mode="incremental", force=True)
        logger.info("Broker bot started")

    async def on_stop(self) -> None:
        from brokerai.integrations.oanda_client import close_oanda_client

        await close_oanda_client()
        logger.info("Broker bot stopped")

    async def status(self) -> dict:
        payload = await super().status()
        payload["last_sync_at"] = self._last_sync_at.isoformat() if self._last_sync_at else None
        payload["open_exit_monitors"] = len(self._monitor._sub_analyzers)
        return payload

    def _require_data_manager(self) -> DataManagerService:
        if self._data_manager is not None:
            return self._data_manager
        return require_data_manager_service()

    async def _refresh_strategies(self) -> None:
        result = await load_runnable_forex_strategies()
        self._strategies_by_id = {
            str(strategy.get("id")): strategy for strategy, _pairs in result.strategies
        }

    def _unprocessed(self, results: list[AnalysisResult]) -> list[AnalysisResult]:
        fresh: list[AnalysisResult] = []
        for analysis in results:
            key = (analysis.strategy_id, analysis.pair)
            if self._processed_analysis_at.get(key) != analysis.analyzed_at:
                fresh.append(analysis)
        return fresh

    def _mark_processed(self, results: list[AnalysisResult]) -> None:
        for analysis in results:
            self._processed_analysis_at[(analysis.strategy_id, analysis.pair)] = analysis.analyzed_at

    async def _strategies_lookup(self, context: PipelineContext) -> dict[str, dict]:
        await self._refresh_strategies()
        by_id = dict(self._strategies_by_id)
        for strategy in context.strategies:
            strategy_id = str(strategy.get("id") or "")
            if strategy_id:
                by_id[strategy_id] = strategy
        return by_id

    async def process_analysis(
        self,
        results: list[AnalysisResult],
        context: PipelineContext,
    ) -> list[TradeIntent]:
        """Event-driven intake from Secretary after Analyst completes."""
        if not results:
            return []

        new_results = self._unprocessed(results)
        if not new_results:
            return []

        actionable = [analysis for analysis in new_results if is_executor_eligible(analysis)]
        skipped = len(new_results) - len(actionable)

        started = time.monotonic()
        await log_pipeline_broker_started(context)

        from brokerai.trading.broker_execution import run_broker_execution

        data_manager = self._require_data_manager()
        intents = await run_broker_execution(
            new_results,
            context,
            data_manager=data_manager,
        )

        pool = get_worker_pool()
        from brokerai.ai_strategy.shadow_dispatch import (
            filter_live_dispatch_intents,
            record_shadow_intents,
        )

        strategies_by_id = await self._strategies_lookup(context)
        live_intents, shadow_intents = filter_live_dispatch_intents(intents, strategies_by_id)
        if shadow_intents:
            await record_shadow_intents(
                shadow_intents,
                strategies_by_id=strategies_by_id,
                context=context,
            )

        for intent in live_intents:
            await log_pipeline_associate_started(context, intent.pair)
            assoc_start = time.monotonic()
            result = await pool.run(AssociateWorker, intent, job_id=context.job_id)
            await log_pipeline_associate_completed(
                context,
                intent.pair,
                int((time.monotonic() - assoc_start) * 1000),
            )
            if not result.ok:
                logger.warning("Associate failed for %s: %s", intent.pair, result.error)

        self._mark_processed(new_results)
        duration_ms = int((time.monotonic() - started) * 1000)
        await log_pipeline_broker_completed(context, duration_ms)
        logger.info(
            "Broker processed %d analysis result(s), %d skipped (no signal), %d live intent(s), %d shadow intent(s) for %s %s",
            len(new_results),
            skipped,
            len(live_intents),
            len(shadow_intents),
            context.symbol,
            context.timeframe,
        )
        return live_intents

    async def tick(self) -> None:
        """Slow tick: account/position sync only — no full re-analysis."""
        self._last_sync_at = utc_now()
        await self._monitor.sync_account_positions()

        snapshot = self._monitor.get_account_snapshot("forex")
        if snapshot:
            logger.debug("Broker sync — forex account connected=%s", snapshot.get("connected"))
