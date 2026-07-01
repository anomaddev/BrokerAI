from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from brokerai.bots.data_analyzer.sub_analyzer import SubAnalyzer
from brokerai.bots.data_manager.candle_requirements import strategy_params
from brokerai.bots.data_manager.service import DataManagerService
from brokerai.config.settings import get_settings
from brokerai.db.repositories.trades import TradesRepository
from brokerai.trading.candle_context import load_candles_for_unit
from brokerai.trading.schedule import utc_now
from brokerai.trading.trade_sync import sync_oanda_trades_to_ledger
from brokerai.trading.indicator_cache import IndicatorCache
from brokerai.trading.registries.exits import create_exit_monitor
from brokerai.trading.types import WorkUnit

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
            requester="broker_exit_monitor",
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


class BrokerMonitor:
    """Open-trade exit monitors and account snapshot consumption."""

    def __init__(self) -> None:
        self._sub_analyzers: dict[str, _TradeExitAnalyzer] = {}
        self._indicator_cache = IndicatorCache()
        self._account_snapshots: dict[str, dict[str, Any]] = {}
        self._last_trade_sync_at: datetime | None = None

    def set_account_snapshot(self, asset_class: str, snapshot: dict[str, Any]) -> None:
        self._account_snapshots[asset_class] = snapshot

    def get_account_snapshot(self, asset_class: str) -> dict[str, Any] | None:
        return self._account_snapshots.get(asset_class)

    async def sync_exit_monitors(
        self,
        work_units: list[WorkUnit],
        data_manager: DataManagerService,
        *,
        evaluate_pairs: set[tuple[str, str]] | None = None,
    ) -> None:
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
                (
                    item
                    for item in unit.strategies
                    if str(item.get("id")) == str(trade.get("strategy_id"))
                ),
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
                    data_manager,
                )

        stale = [tid for tid in self._sub_analyzers if tid not in active_ids]
        for tid in stale:
            del self._sub_analyzers[tid]

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

    async def _maybe_sync_oanda_trades(self) -> None:
        settings = get_settings()
        now = utc_now()
        if self._last_trade_sync_at is not None:
            elapsed = (now - self._last_trade_sync_at).total_seconds()
            if elapsed < settings.trade_sync_interval_seconds:
                return

        self._last_trade_sync_at = now
        result = await sync_oanda_trades_to_ledger()
        if not result.get("configured"):
            return
        imported = int(result.get("imported", 0))
        updated = int(result.get("updated", 0))
        closed = int(result.get("closed", 0))
        backfilled = int(result.get("backfilled", 0))
        if imported or updated or closed or backfilled:
            logger.info(
                "Broker monitor — OANDA trade sync imported=%d updated=%d closed=%d backfilled=%d",
                imported,
                updated,
                closed,
                backfilled,
            )

    async def sync_account_positions(self) -> None:
        """Slow-tick housekeeping: import broker-only open trades into the ledger."""
        await self._maybe_sync_oanda_trades()
        open_trades = await TradesRepository().list_open_trades()
        logger.debug("Broker monitor — %d open trade(s)", len(open_trades))
