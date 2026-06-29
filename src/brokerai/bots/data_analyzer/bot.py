from __future__ import annotations

import asyncio
import logging

from brokerai.bots.base import Bot
from brokerai.bots.data_analyzer.sub_analyzer import SubAnalyzer
from brokerai.bots.data_manager.candle_requirements import strategy_params
from brokerai.bots.data_manager.candles import OANDA_SOURCE
from brokerai.bots.data_manager.service import DataManagerService
from brokerai.db.repositories.trades import TradesRepository
from brokerai.trading.asset_runtime import get_asset_runtime
from brokerai.trading.candle_context import load_candles_for_unit
from brokerai.trading.candle_revision import GLOBAL_CANDLE_REVISIONS
from brokerai.trading.indicator_cache import IndicatorCache
from brokerai.trading.pipeline import log_analysis_result, run_strategy_analysis
from brokerai.trading.registries.exits import create_exit_monitor
from brokerai.trading.schedule import utc_now
from brokerai.trading.types import AnalysisResult, WorkUnit

logger = logging.getLogger(__name__)


class _TradeExitAnalyzer(SubAnalyzer):
    def __init__(
        self,
        trade: dict,
        params: dict,
        unit: WorkUnit,
        indicator_cache: IndicatorCache,
        data_manager: DataManagerService,
    ) -> None:
        super().__init__(str(trade.get("id", "")))
        self._trade = trade
        self._params = params
        self._unit = unit
        self._indicator_cache = indicator_cache
        self._data_manager = data_manager
        self._monitor = create_exit_monitor(trade, params)

    async def evaluate(self) -> None:
        if self._monitor is None:
            return
        candles = await load_candles_for_unit(
            self._unit,
            service=self._data_manager,
            requester="data_analyzer_exit",
        )
        if not candles:
            return
        cache = self._indicator_cache.warm(
            self._unit.pair,
            self._unit.timeframe,
            candles,
            [self._params],
        )
        exit_intent = await self._monitor.evaluate(self._trade, candles, self._params, cache)
        if exit_intent is None:
            return
        logger.info(
            "ExitIntent trade=%s pair=%s reason=%s",
            exit_intent.trade_id,
            exit_intent.pair,
            exit_intent.reason,
        )
        await TradesRepository().close_trade(
            exit_intent.trade_id,
            reason=exit_intent.reason,
            metadata=exit_intent.metadata,
        )


class DataAnalyzerBot(Bot):
    name = "data_analyzer"

    def __init__(self) -> None:
        super().__init__()
        self._data_manager: DataManagerService | None = None
        self._indicator_cache = IndicatorCache()
        self._last_run_at = None
        self._last_results: dict[tuple[str, str], AnalysisResult] = {}
        self._sub_analyzers: dict[str, SubAnalyzer] = {}

    def attach_data_manager(self, service: DataManagerService) -> None:
        self._data_manager = service

    async def on_start(self) -> None:
        logger.info("Data Analyzer bot started")

    async def run_startup_pass(self) -> None:
        """Analyze cached candles once at startup, then wait for new bars."""
        logger.info("Data Analyzer — running startup analysis pass")
        await self.tick()

    async def on_stop(self) -> None:
        logger.info("Data Analyzer bot stopped")

    async def status(self) -> dict:
        payload = await super().status()
        payload["last_run_at"] = self._last_run_at.isoformat() if self._last_run_at else None
        payload["recent_results_count"] = len(self._last_results)
        payload["data_manager_attached"] = self._data_manager is not None
        payload["last_analyzed_candles"] = GLOBAL_CANDLE_REVISIONS.snapshot()
        return payload

    def _require_data_manager(self) -> DataManagerService:
        if self._data_manager is None:
            raise RuntimeError("Data Manager is not attached — enable the data_manager bot")
        return self._data_manager

    async def _sync_exit_monitors(
        self,
        work_units: list[WorkUnit],
        *,
        evaluate_pairs: set[tuple[str, str]] | None = None,
    ) -> None:
        if self._data_manager is None:
            return

        open_trades = await TradesRepository().list_open_trades()
        units_by_pair: dict[str, WorkUnit] = {unit.pair: unit for unit in work_units}
        active_ids: set[str] = set()

        for trade in open_trades:
            trade_id = str(trade.get("id", ""))
            pair = str(trade.get("pair", ""))
            unit = units_by_pair.get(pair)
            if not unit:
                continue
            strategy = next(
                (item for item in unit.strategies if str(item.get("id")) == str(trade.get("strategy_id"))),
                None,
            )
            if strategy is None:
                continue
            params = strategy_params(strategy)
            active_ids.add(trade_id)
            if trade_id not in self._sub_analyzers:
                self._sub_analyzers[trade_id] = _TradeExitAnalyzer(
                    trade,
                    params,
                    unit,
                    self._indicator_cache,
                    self._data_manager,
                )

        stale = [trade_id for trade_id in self._sub_analyzers if trade_id not in active_ids]
        for trade_id in stale:
            del self._sub_analyzers[trade_id]

        if not evaluate_pairs or not self._sub_analyzers:
            return

        analyzers = [
            analyzer
            for analyzer in self._sub_analyzers.values()
            if (analyzer._unit.pair, analyzer._unit.timeframe) in evaluate_pairs
        ]
        if analyzers:
            await asyncio.gather(
                *[analyzer.evaluate() for analyzer in analyzers],
                return_exceptions=True,
            )

    async def tick(self) -> None:
        if self._data_manager is None:
            logger.debug("Data Analyzer tick — Data Manager not attached")
            return

        runtime = get_asset_runtime("forex")
        if runtime is None:
            logger.debug("Data Analyzer tick — no asset runtimes registered")
            return

        result = await runtime.load_runnable_strategies()
        if result.skip_reason:
            logger.info("Data Analyzer tick — %s", result.skip_reason)
            return

        work_plan = runtime.build_work_plan(result.strategies)
        if not work_plan.units:
            logger.info("Data Analyzer tick — no work units")
            return

        data_manager = self._require_data_manager()
        now = utc_now()
        units_with_new_candles: list[WorkUnit] = []

        for unit in work_plan.units:
            latest_time = await data_manager.latest_candle_time(
                unit.pair,
                unit.timeframe,
                source=OANDA_SOURCE,
            )
            if not latest_time:
                continue
            if not GLOBAL_CANDLE_REVISIONS.has_changed(unit.pair, unit.timeframe, latest_time):
                logger.debug(
                    "Data Analyzer — skipping %s %s (no new candle)",
                    unit.pair,
                    unit.timeframe,
                )
                continue
            units_with_new_candles.append(unit)

        await self._sync_exit_monitors(list(work_plan.units))

        if not units_with_new_candles:
            logger.debug("Data Analyzer tick — no new candles to analyze")
            return

        analyzed_any = False
        evaluated_pairs: set[tuple[str, str]] = set()

        for unit in units_with_new_candles:
            latest_time = await data_manager.latest_candle_time(
                unit.pair,
                unit.timeframe,
                source=OANDA_SOURCE,
            )
            candles = await load_candles_for_unit(
                unit,
                service=data_manager,
                requester="data_analyzer",
            )
            if not candles:
                logger.warning(
                    "Data Analyzer — no candles for %s %s",
                    unit.pair,
                    unit.timeframe,
                )
                continue

            cache = self._indicator_cache.warm(
                unit.pair,
                unit.timeframe,
                candles,
                [strategy_params(strategy) for strategy in unit.strategies],
            )

            for strategy in unit.strategies:
                analysis = run_strategy_analysis(
                    strategy,
                    unit.pair,
                    candles,
                    cache,
                    timeframe=unit.timeframe,
                )
                log_analysis_result(analysis)
                self._last_results[(analysis.strategy_id, unit.pair)] = analysis
                analyzed_any = True

            GLOBAL_CANDLE_REVISIONS.mark_updated(unit.pair, unit.timeframe, latest_time)
            evaluated_pairs.add((unit.pair, unit.timeframe))
            logger.info(
                "Data Analyzer — analyzed %s %s through %s",
                unit.pair,
                unit.timeframe,
                latest_time,
            )

        if analyzed_any:
            self._last_run_at = now

        await self._sync_exit_monitors(list(work_plan.units), evaluate_pairs=evaluated_pairs)

    def get_recent_results(self) -> list[AnalysisResult]:
        return list(self._last_results.values())
