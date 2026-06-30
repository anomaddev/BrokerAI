from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from brokerai.bots.base import Bot
from brokerai.bots.data_manager.candle_requirements import required_candle_bars, strategy_params, strategy_timeframe
from brokerai.bots.data_manager.candles import OANDA_SOURCE
from brokerai.bots.data_manager.forex_strategies import load_runnable_forex_strategies
from brokerai.bots.data_manager.service import DataManagerService
from brokerai.db.repositories.asset_settings import AssetSettingsRepository
from brokerai.db.repositories.strategy_analysis_runs import StrategyAnalysisRunsRepository
from brokerai.db.repositories.trades import TradesRepository
from brokerai.trading.ai_confirmation import maybe_confirm_trade_intent
from brokerai.trading.execution_gates import passes_execution_gates, resolve_priority_conflicts
from brokerai.trading.pipeline import ensure_trading_registries
from brokerai.trading.schedule import utc_now
from brokerai.trading.types import AnalysisResult, TradeIntent

if TYPE_CHECKING:
    from brokerai.bots.data_analyzer.bot import DataAnalyzerBot

logger = logging.getLogger(__name__)


class ExecutorBot(Bot):
    name = "executor"

    def __init__(self) -> None:
        super().__init__()
        self._pending_intents: list[TradeIntent] = []
        self._last_processed_at: str | None = None
        self._data_analyzer: DataAnalyzerBot | None = None
        self._data_manager: DataManagerService | None = None
        self._strategies_by_id: dict[str, dict] = {}
        self._processed_analysis_at: dict[tuple[str, str], datetime | None] = {}

    def attach_data_analyzer(self, bot: DataAnalyzerBot) -> None:
        self._data_analyzer = bot

    def attach_data_manager(self, service: DataManagerService) -> None:
        self._data_manager = service

    async def on_start(self) -> None:
        ensure_trading_registries()
        self._processed_analysis_at.clear()
        logger.info("Executor bot started")

    async def run_startup_pass(self) -> None:
        """Process the initial analysis results once after startup."""
        logger.info("Executor — running startup execution pass")
        await self.tick()

    async def on_stop(self) -> None:
        logger.info("Executor bot stopped")

    async def status(self) -> dict:
        payload = await super().status()
        payload["pending_intents"] = len(self._pending_intents)
        payload["last_processed_at"] = self._last_processed_at
        payload["data_manager_attached"] = self._data_manager is not None
        return payload

    async def _refresh_strategies(self) -> None:
        result = await load_runnable_forex_strategies()
        self._strategies_by_id = {
            str(strategy.get("id")): strategy for strategy, _pairs in result.strategies
        }

    async def _load_candles(self, strategy: dict, pair: str) -> list[dict]:
        if self._data_manager is None:
            logger.warning("Executor — Data Manager not attached; cannot load candles")
            return []
        timeframe = strategy_timeframe(strategy)
        if not timeframe:
            return []
        return await self._data_manager.request_candles(
            pair,
            timeframe,
            bar_count=required_candle_bars(strategy),
            source=OANDA_SOURCE,
            requester="executor",
        )

    def _unprocessed_results(self, results: list[AnalysisResult]) -> list[AnalysisResult]:
        fresh: list[AnalysisResult] = []
        for analysis in results:
            key = (analysis.strategy_id, analysis.pair)
            if self._processed_analysis_at.get(key) != analysis.analyzed_at:
                fresh.append(analysis)
        return fresh

    def _mark_processed(self, results: list[AnalysisResult]) -> None:
        for analysis in results:
            self._processed_analysis_at[(analysis.strategy_id, analysis.pair)] = analysis.analyzed_at

    def _serialize_intent(self, intent: TradeIntent | None) -> dict | None:
        if intent is None:
            return None
        return {
            "direction": intent.direction,
            "entry_price": intent.entry_price,
            "stop_loss": intent.stop_loss,
            "take_profit": intent.take_profit,
            "confidence": intent.confidence,
        }

    async def _persist_execution_outcome(
        self,
        analysis: AnalysisResult,
        *,
        processed_at: datetime,
        gates_passed: bool,
        gate_reasons: list[str],
        priority_winner: bool,
        intent_queued: bool,
        intent: TradeIntent | None,
    ) -> None:
        if not analysis.run_id:
            return
        execution = {
            "processed_at": processed_at.isoformat(),
            "gates_passed": gates_passed,
            "gate_reasons": gate_reasons,
            "priority_winner": priority_winner,
            "intent_queued": intent_queued,
            "intent": self._serialize_intent(intent),
        }
        await StrategyAnalysisRunsRepository().update_execution(analysis.run_id, execution)

    async def tick(self) -> None:
        if self._data_analyzer is None:
            logger.debug("Executor tick — no data analyzer attached")
            return
        if self._data_manager is None:
            logger.debug("Executor tick — Data Manager not attached")
            return

        results = self._data_analyzer.get_recent_results()
        if not results:
            logger.debug("Executor tick — no analysis results")
            return

        new_results = self._unprocessed_results(results)
        if not new_results:
            logger.debug("Executor tick — no new analysis results")
            return

        await self._refresh_strategies()
        trade_counts = await TradesRepository().daily_trade_counts()
        forex_settings = await AssetSettingsRepository().get("forex")
        asset_enabled_sessions = forex_settings.get("enabled_sessions")
        gated: list[tuple[AnalysisResult, dict, dict]] = []
        now = utc_now()

        for analysis in new_results:
            strategy = self._strategies_by_id.get(analysis.strategy_id)
            if strategy is None:
                continue
            params = strategy_params(strategy)
            passed, reasons = passes_execution_gates(
                analysis,
                params,
                trade_counts,
                when=now,
                asset_enabled_sessions=asset_enabled_sessions,
            )
            if passed:
                gated.append((analysis, params, strategy))
            else:
                logger.info(
                    "Executor — gated out %s %s: %s",
                    analysis.strategy_name,
                    analysis.pair,
                    ",".join(reasons),
                )
                await self._persist_execution_outcome(
                    analysis,
                    processed_at=now,
                    gates_passed=False,
                    gate_reasons=reasons,
                    priority_winner=False,
                    intent_queued=False,
                    intent=None,
                )

        winners = resolve_priority_conflicts([(analysis, params) for analysis, params, _ in gated])
        winner_ids = {(analysis.strategy_id, analysis.pair) for analysis, _ in winners}

        intents: list[TradeIntent] = []
        for analysis, params, strategy in gated:
            key = (analysis.strategy_id, analysis.pair)
            if key not in winner_ids:
                await self._persist_execution_outcome(
                    analysis,
                    processed_at=now,
                    gates_passed=True,
                    gate_reasons=[],
                    priority_winner=False,
                    intent_queued=False,
                    intent=None,
                )
                continue
            candles = await self._load_candles(strategy, analysis.pair)
            intent = await maybe_confirm_trade_intent(
                analysis,
                params,
                candles,
                asset_class="forex",
            )
            if intent is not None:
                intents.append(intent)
                logger.info(
                    "Executor — trade intent %s %s %s confidence=%.2f sl=%s tp=%s",
                    intent.strategy_name,
                    intent.pair,
                    intent.direction,
                    intent.confidence,
                    intent.stop_loss,
                    intent.take_profit,
                )
            await self._persist_execution_outcome(
                analysis,
                processed_at=now,
                gates_passed=True,
                gate_reasons=[],
                priority_winner=True,
                intent_queued=intent is not None,
                intent=intent,
            )

        self._pending_intents = intents
        self._last_processed_at = now.isoformat()
        self._mark_processed(new_results)
        logger.info("Executor tick — %d trade intent(s) queued", len(intents))

    def consume_pending_intents(self) -> list[TradeIntent]:
        intents = list(self._pending_intents)
        self._pending_intents.clear()
        return intents
