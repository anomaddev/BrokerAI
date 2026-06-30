import logging
from dataclasses import replace
from datetime import datetime, timezone

from brokerai.bots.base import Bot
from brokerai.bots.data_manager.candle_requirements import CandleRequirement, collect_candle_requirements
from brokerai.bots.data_manager.candle_schedule import is_candle_fetch_due, next_candle_close_at
from brokerai.bots.data_manager.candle_watch import collect_watch_requirements
from brokerai.bots.data_manager.candles import (
    OANDA_SOURCE,
    fetch_and_cache_forex_candles,
    requirement_needs_bootstrap,
)
from brokerai.bots.data_manager.forex_strategies import load_runnable_forex_strategies
from brokerai.bots.data_manager.service import DataManagerService, set_data_manager_service

logger = logging.getLogger(__name__)


def _format_forex_strategy(strategy: dict, matched_pairs: list[str]) -> str:
    preset = strategy.get("preset_id") or strategy.get("strategy_type") or "custom"
    timeframe = strategy.get("timeframe") or "—"
    pairs_label = ", ".join(matched_pairs) if matched_pairs else "—"
    return (
        f"{strategy['name']} ({strategy['id'][:8]}…) · {preset} · "
        f"{timeframe} · {pairs_label}"
    )


class DataManagerBot(Bot):
    name = "data_manager"

    def __init__(self) -> None:
        super().__init__()
        self._next_fetch_at: dict[str, datetime] = {}
        self._service = DataManagerService()

    @property
    def service(self) -> DataManagerService:
        return self._service

    async def on_start(self) -> None:
        set_data_manager_service(self._service)
        logger.info("Data Manager bot started")

    async def on_stop(self) -> None:
        set_data_manager_service(None)
        logger.info("Data Manager bot stopped")

    async def status(self) -> dict:
        payload = await super().status()
        now = datetime.now(timezone.utc)
        fetches = dict(self._next_fetch_at)
        if not fetches:
            from brokerai.config.settings import get_settings

            for timeframe in get_settings().candle_default_timeframes.split(","):
                tf = timeframe.strip()
                if tf:
                    fetches[tf] = next_candle_close_at(now, tf)
        payload["next_candle_fetches"] = {
            timeframe: when.isoformat()
            for timeframe, when in sorted(fetches.items())
        }
        payload["registered_demand"] = [
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "source": source,
                "bar_count": bar_count,
            }
            for symbol, timeframe, source, bar_count in self._service.registered_demand()
        ]
        return payload

    def _schedule_next_fetch(self, timeframe: str, *, now: datetime | None = None) -> datetime:
        when = now or datetime.now(timezone.utc)
        next_at = next_candle_close_at(when, timeframe)
        self._next_fetch_at[timeframe] = next_at
        return next_at

    async def _plan_fetches(self, requirements, watch_requirements: list[CandleRequirement]):
        now = datetime.now(timezone.utc)
        bootstrap = []
        incremental = []
        waiting = []
        all_requirements = list(requirements) + list(watch_requirements)

        for requirement in all_requirements:
            if await requirement_needs_bootstrap(requirement, self._service):
                bootstrap.append(requirement)
                if self._next_fetch_at.get(requirement.timeframe) is None:
                    self._schedule_next_fetch(requirement.timeframe, now=now)
                    incremental.append(replace(requirement, incremental=True))
                continue

            next_at = self._next_fetch_at.get(requirement.timeframe)
            if next_at is None:
                next_at = self._schedule_next_fetch(requirement.timeframe, now=now)
                incremental.append(replace(requirement, incremental=True))
                continue

            if is_candle_fetch_due(now, next_at):
                incremental.append(replace(requirement, incremental=True))
            else:
                waiting.append((requirement, next_at))

        for symbol, timeframe, _source, bar_count in self._service.registered_demand():
            demand_req = CandleRequirement(
                timeframe=timeframe,
                pairs=(symbol,),
                bar_count=bar_count,
            )
            if await requirement_needs_bootstrap(demand_req, self._service):
                bootstrap.append(demand_req)
                if self._next_fetch_at.get(timeframe) is None:
                    self._schedule_next_fetch(timeframe, now=now)
                    incremental.append(replace(demand_req, incremental=True))
                continue
            next_at = self._next_fetch_at.get(timeframe)
            if next_at is None:
                next_at = self._schedule_next_fetch(timeframe, now=now)
                incremental.append(replace(demand_req, incremental=True))
                continue
            if is_candle_fetch_due(now, next_at):
                incremental.append(replace(demand_req, incremental=True))

        return bootstrap, incremental, waiting

    async def tick(self) -> None:
        result = await load_runnable_forex_strategies()
        watch_requirements = await collect_watch_requirements()

        if result.skip_reason:
            if not watch_requirements and not self._service.registered_demand():
                logger.info("Data Manager tick — %s", result.skip_reason)
                return
            logger.info(
                "Data Manager tick — %s; continuing for %d watch(es)",
                result.skip_reason,
                len(watch_requirements),
            )
            requirements: list[CandleRequirement] = []
            warnings: list[str] = []
        else:
            count = len(result.strategies)
            logger.debug(
                "Data Manager tick — %d forex strateg%s with enabled pairs",
                count,
                "y" if count == 1 else "ies",
            )
            for strategy, matched_pairs in result.strategies:
                logger.debug("  %s", _format_forex_strategy(strategy, matched_pairs))

            requirements, warnings = collect_candle_requirements(result.strategies)
            for warning in warnings:
                logger.warning("Data Manager — %s", warning)

        if not requirements and not watch_requirements and not self._service.registered_demand():
            logger.info("Data Manager tick — no candle requirements to fetch")
            return

        bootstrap, incremental, waiting = await self._plan_fetches(
            requirements,
            watch_requirements,
        )

        for requirement, next_at in waiting:
            logger.debug(
                "Data Manager — %s next fetch scheduled at %s",
                requirement.timeframe,
                next_at.isoformat(),
            )

        to_fetch = bootstrap + incremental
        if not to_fetch:
            logger.debug("Data Manager tick — no candle fetches due")
            return

        if bootstrap:
            logger.info(
                "Data Manager tick — bootstrapping %d timeframe(s)",
                len(bootstrap),
            )
            for requirement in bootstrap:
                pairs_label = ", ".join(requirement.pairs) if requirement.pairs else "—"
                logger.info(
                    "  bootstrap %s · %s · %d bars",
                    requirement.timeframe,
                    pairs_label,
                    requirement.bar_count,
                )

        if incremental:
            logger.info(
                "Data Manager tick — incremental fetch for %d timeframe(s)",
                len(incremental),
            )
            for requirement in incremental:
                pairs_label = ", ".join(requirement.pairs) if requirement.pairs else "—"
                logger.info("  incremental %s · %s", requirement.timeframe, pairs_label)

        fetch_result = await fetch_and_cache_forex_candles(to_fetch, service=self._service)
        now = datetime.now(timezone.utc)
        for requirement in to_fetch:
            next_at = self._schedule_next_fetch(requirement.timeframe, now=now)
            logger.info(
                "Data Manager — %s next closed-candle fetch at %s",
                requirement.timeframe,
                next_at.isoformat(),
            )

        if fetch_result.candles_upserted:
            logger.info(
                "Data Manager tick — upserted %d candle(s) across %d/%d timeframe(s)",
                fetch_result.candles_upserted,
                fetch_result.fetched,
                len(to_fetch),
            )
        elif fetch_result.fetched:
            logger.info(
                "Data Manager tick — refreshed %d/%d timeframe(s)",
                fetch_result.fetched,
                len(to_fetch),
            )
        for error in fetch_result.errors:
            logger.warning("Data Manager — %s", error)
