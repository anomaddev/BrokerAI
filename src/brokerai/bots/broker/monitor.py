from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from brokerai.bots.data_manager.candle_requirements import strategy_params
from brokerai.bots.data_manager.service import DataManagerService
from brokerai.config.settings import get_settings
from brokerai.db.repositories.broker_lots import BrokerLotsRepository
from brokerai.trading.broker.state import BrokerStateService
from brokerai.trading.candle_context import load_candles_for_unit
from brokerai.trading.broker.sync import run_broker_sync
from brokerai.trading.exit_analysis import persist_exit_analysis_run, trade_requires_exit_monitor
from brokerai.trading.indicator_cache import IndicatorCache
from brokerai.trading.registries.exits import create_exit_monitor
from brokerai.trading.schedule import utc_now
from brokerai.trading.types import ExitIntent, WorkUnit

logger = logging.getLogger(__name__)


class _SubAnalyzer(ABC):
    trade_id: str

    def __init__(self, trade_id: str) -> None:
        self.trade_id = trade_id

    @abstractmethod
    async def evaluate(self) -> None:
        """Evaluate exit signals for a monitored trade."""


async def _close_lot(
    lots_repo: BrokerLotsRepository,
    trade_id: str,
    *,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    lot = await lots_repo.get_by_id(trade_id)
    if lot is None:
        return
    exit_candle_open = (metadata or {}).get("exit_candle_open")
    if lot.get("state") == "open" and lot.get("broker_lot_id"):
        await BrokerStateService(lots_repo=lots_repo).close_lot(
            str(lot.get("exchange_id", "oanda")),
            trade_id,
            reason=reason,
            close_metadata=metadata,
            exit_candle_open=exit_candle_open,
        )
        return
    await lots_repo.close_lot(
        trade_id,
        reason=reason,
        exit_candle_open=exit_candle_open,
        close_metadata=metadata,
    )


class _TradeExitAnalyzer(_SubAnalyzer):
    def __init__(
        self,
        trade: dict,
        params: dict,
        unit: WorkUnit,
        indicator_cache: IndicatorCache,
        data_manager: DataManagerService,
        lots_repo: BrokerLotsRepository,
    ) -> None:
        super().__init__(str(trade.get("id", "")))
        self._trade = trade
        self._params = params
        self._unit = unit
        self._indicator_cache = indicator_cache
        self._data_manager = data_manager
        self._lots_repo = lots_repo
        self._monitor = create_exit_monitor(trade, params)

    async def evaluate(self) -> ExitIntent | None:
        if self._monitor is None:
            return None
        candles = await load_candles_for_unit(
            self._unit,
            service=self._data_manager,
            requester="broker_exit_monitor",
        )
        if not candles:
            return None
        cache = self._indicator_cache.warm(
            self._unit.pair,
            self._unit.timeframe,
            candles,
            [self._params],
        )
        exit_intent = await self._monitor.evaluate(self._trade, candles, self._params, cache)
        candle_time = candles[-1].get("time") if candles else None
        signal_metadata = dict(exit_intent.metadata or {}) if exit_intent else {"signal": "none"}

        strategy = next(
            (
                item
                for item in self._unit.strategies
                if str(item.get("id")) == str(self._trade.get("strategy_id"))
            ),
            {"id": self._trade.get("strategy_id"), "name": self._trade.get("strategy_name")},
        )

        exit_closed = False
        if exit_intent is not None:
            logger.info(
                "ExitIntent trade=%s pair=%s reason=%s",
                exit_intent.trade_id,
                exit_intent.pair,
                exit_intent.reason,
            )
            close_metadata = dict(exit_intent.metadata or {})
            if candle_time:
                close_metadata["exit_candle_open"] = candle_time
            await _close_lot(
                self._lots_repo,
                exit_intent.trade_id,
                reason=exit_intent.reason,
                metadata=close_metadata,
            )
            exit_closed = True

        await persist_exit_analysis_run(
            self._trade,
            strategy,
            timeframe=self._unit.timeframe,
            exit_intent=exit_intent,
            signal_metadata=signal_metadata,
            candle_time=candle_time,
            exit_closed=exit_closed,
        )
        return exit_intent


class BrokerMonitor:
    """Open-trade exit monitors and account snapshot consumption."""

    def __init__(self) -> None:
        self._sub_analyzers: dict[str, _TradeExitAnalyzer] = {}
        self._indicator_cache = IndicatorCache()
        self._account_snapshots: dict[str, dict[str, Any]] = {}
        self._last_trade_sync_at: datetime | None = None
        self._lots_repo = BrokerLotsRepository()

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
        open_trades = await self._lots_repo.list_open_lots()
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
            if not trade_requires_exit_monitor(params):
                continue
            if create_exit_monitor(trade, params) is None:
                continue
            active_ids.add(trade_id)
            if trade_id not in self._sub_analyzers:
                self._sub_analyzers[trade_id] = _TradeExitAnalyzer(
                    trade,
                    params,
                    unit,
                    self._indicator_cache,
                    data_manager,
                    self._lots_repo,
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
        result = await run_broker_sync(
            exchange_id="oanda",
            mode="incremental",
            include_account_summary=True,
            fetch_live_prices=True,
        )
        if not result.configured:
            return
        imported = int(result.lots_upserted)
        updated = int(result.enriched)
        closed = int(result.lots_closed)
        if imported or updated or closed:
            logger.info(
                "Broker monitor — broker sync lots=%d enriched=%d closed=%d",
                imported,
                updated,
                closed,
            )

    async def sync_account_positions(self) -> None:
        """Slow-tick housekeeping: import broker-only open trades into the ledger."""
        await self._maybe_sync_oanda_trades()
        open_trades = await self._lots_repo.list_open_lots()
        logger.debug("Broker monitor — %d open trade(s)", len(open_trades))
