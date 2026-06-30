from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import datetime, timezone

from brokerai.bots.data_manager.candle_requirements import CandleRequirement, collect_candle_requirements
from brokerai.bots.data_manager.candle_schedule import is_candle_fetch_due, next_candle_close_at
from brokerai.bots.data_manager.candle_watch import collect_watch_requirements
from brokerai.bots.data_manager.candles import requirement_needs_bootstrap
from brokerai.bots.data_manager.forex_strategies import load_runnable_forex_strategies
from brokerai.bots.data_manager.service import DataManagerService, require_data_manager_service
from brokerai.bots.secretary.types import CandleJob
from brokerai.config.settings import get_settings
from brokerai.trading.asset_runtime import get_asset_runtime
from brokerai.trading.candle_revision import GLOBAL_CANDLE_REVISIONS
from brokerai.trading.work_plan import build_work_plan

logger = logging.getLogger(__name__)


class CandleTimeline:
    """Builds candle requirements and detects due close jobs for Secretary."""

    def __init__(self) -> None:
        self._next_fetch_at: dict[str, datetime] = {}

    def snapshot_next_fetches(self) -> dict[str, str]:
        now = datetime.now(timezone.utc)
        fetches = dict(self._next_fetch_at)
        if not fetches:
            for timeframe in get_settings().candle_default_timeframes.split(","):
                tf = timeframe.strip()
                if tf:
                    fetches[tf] = next_candle_close_at(now, tf)
        return {tf: when.isoformat() for tf, when in sorted(fetches.items())}

    def _schedule_next_fetch(self, timeframe: str, *, now: datetime | None = None) -> datetime:
        when = now or datetime.now(timezone.utc)
        next_at = next_candle_close_at(when, timeframe)
        self._next_fetch_at[timeframe] = next_at
        return next_at

    async def build_due_jobs(
        self,
        service: DataManagerService,
        *,
        now: datetime | None = None,
    ) -> tuple[list[CandleJob], list[str]]:
        """Return CandleJobs due for pipeline dispatch and any planning warnings."""
        when = now or datetime.now(timezone.utc)
        warnings: list[str] = []
        result = await load_runnable_forex_strategies()
        watch_requirements = await collect_watch_requirements()

        if result.skip_reason and not watch_requirements and not service.registered_demand():
            return [], [result.skip_reason]

        if result.skip_reason:
            requirements: list[CandleRequirement] = []
        else:
            requirements, warnings = collect_candle_requirements(result.strategies)

        all_requirements = list(requirements) + list(watch_requirements)
        for symbol, timeframe, _source, bar_count in service.registered_demand():
            all_requirements.append(
                CandleRequirement(timeframe=timeframe, pairs=(symbol,), bar_count=bar_count)
            )

        if not all_requirements:
            return [], warnings

        due_units: list[tuple[str, str, int, bool, bool]] = []

        for requirement in all_requirements:
            needs_bootstrap = await requirement_needs_bootstrap(requirement, service)
            next_at = self._next_fetch_at.get(requirement.timeframe)
            if next_at is None:
                next_at = self._schedule_next_fetch(requirement.timeframe, now=when)

            fetch_due = needs_bootstrap or is_candle_fetch_due(when, next_at)
            if not fetch_due:
                continue

            for pair in requirement.pairs:
                due_units.append(
                    (
                        pair,
                        requirement.timeframe,
                        requirement.bar_count,
                        needs_bootstrap,
                        not needs_bootstrap,
                    )
                )

            if fetch_due:
                self._schedule_next_fetch(requirement.timeframe, now=when)

        if not due_units and result.strategies:
            runtime = get_asset_runtime("forex")
            if runtime is not None:
                work_plan = runtime.build_work_plan(result.strategies)
                for unit in work_plan.units:
                    latest = await service.latest_candle_time(
                        unit.pair,
                        unit.timeframe,
                        source="oanda",
                    )
                    if latest and GLOBAL_CANDLE_REVISIONS.has_changed(
                        unit.pair, unit.timeframe, latest
                    ):
                        due_units.append(
                            (unit.pair, unit.timeframe, unit.bar_count, False, True)
                        )

        jobs: list[CandleJob] = []
        if result.strategies:
            work_plan = build_work_plan(result.strategies, asset_class="forex")
            units_by_key = {
                (u.pair, u.timeframe): u for u in work_plan.units
            }
        else:
            units_by_key = {}

        seen: set[str] = set()
        trigger_time = when
        for pair, timeframe, bar_count, bootstrap, incremental in due_units:
            unit = units_by_key.get((pair, timeframe))
            strategies = tuple(unit.strategies) if unit else ()
            if not strategies and not bootstrap:
                continue

            latest = await service.latest_candle_time(pair, timeframe, source="oanda")
            if latest and not GLOBAL_CANDLE_REVISIONS.has_changed(pair, timeframe, latest):
                if not bootstrap:
                    continue

            dedupe = f"{pair}|{timeframe}|{trigger_time.isoformat()}"
            if dedupe in seen:
                continue
            seen.add(dedupe)

            jobs.append(
                CandleJob(
                    job_id=str(uuid.uuid4()),
                    asset_class="forex",
                    symbol=pair,
                    timeframe=timeframe,
                    bar_count=bar_count if unit is None else unit.bar_count,
                    trigger_time=trigger_time,
                    strategies=strategies if strategies else ((),),
                    incremental=incremental,
                    bootstrap=bootstrap,
                )
            )

        return jobs, warnings

    async def build_startup_jobs(self, service: DataManagerService) -> list[CandleJob]:
        """Warm-up jobs for incomplete cache or unmarked revisions."""
        result = await load_runnable_forex_strategies()
        if result.skip_reason:
            return []

        runtime = get_asset_runtime("forex")
        if runtime is None:
            return []

        work_plan = runtime.build_work_plan(result.strategies)
        when = datetime.now(timezone.utc)
        jobs: list[CandleJob] = []

        for unit in work_plan.units:
            req = CandleRequirement(
                timeframe=unit.timeframe,
                pairs=(unit.pair,),
                bar_count=unit.bar_count,
            )
            needs_bootstrap = await requirement_needs_bootstrap(req, service)
            latest = await service.latest_candle_time(unit.pair, unit.timeframe, source="oanda")
            needs_analysis = latest and GLOBAL_CANDLE_REVISIONS.has_changed(
                unit.pair, unit.timeframe, latest
            )
            if not needs_bootstrap and not needs_analysis:
                continue

            jobs.append(
                CandleJob(
                    job_id=str(uuid.uuid4()),
                    asset_class=unit.asset_class,
                    symbol=unit.pair,
                    timeframe=unit.timeframe,
                    bar_count=unit.bar_count,
                    trigger_time=when,
                    strategies=unit.strategies,
                    incremental=not needs_bootstrap,
                    bootstrap=needs_bootstrap,
                )
            )

        return jobs
