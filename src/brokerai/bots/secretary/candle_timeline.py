from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from brokerai.bots.data_manager.candle_requirements import CandleRequirement, collect_candle_requirements
from brokerai.bots.data_manager.candle_schedule import is_candle_fetch_due, next_candle_close_at
from brokerai.bots.data_manager.candle_watch import collect_watch_requirements
from brokerai.bots.data_manager.candles import requirement_needs_bootstrap, requirement_needs_warmup
from brokerai.bots.data_manager.forex_strategies import load_runnable_forex_strategies
from brokerai.bots.data_manager.service import DataManagerService, require_data_manager_service
from brokerai.bots.secretary.types import CandleJob
from brokerai.config.settings import get_settings
from brokerai.trading.asset_runtime import get_asset_runtime
from brokerai.trading.candle_revision import GLOBAL_CANDLE_REVISIONS
from brokerai.trading.data.market_calendar import expected_latest_closed_bar
from brokerai.trading.work_plan import build_work_plan

logger = logging.getLogger(__name__)

# How long to suppress strategy reloads after a stable idle skip (no strategies,
# watches, or registered candle demand). Recheck periodically so config changes
# are picked up without polling Postgres every secretary tick.
_PIPELINE_IDLE_RECHECK = timedelta(seconds=60)


class CandleTimeline:
    """Builds candle requirements and detects due close jobs for Secretary."""

    def __init__(self) -> None:
        self._next_fetch_at: dict[str, datetime] = {}
        self._pipeline_idle_reason: str | None = None
        self._pipeline_idle_until: datetime | None = None

    def _clear_pipeline_idle(self) -> None:
        self._pipeline_idle_reason = None
        self._pipeline_idle_until = None

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

        if service.registered_demand():
            self._clear_pipeline_idle()
        elif (
            self._pipeline_idle_reason is not None
            and self._pipeline_idle_until is not None
            and when < self._pipeline_idle_until
        ):
            return [], []

        warnings: list[str] = []
        watch_requirements = await collect_watch_requirements()
        result = await load_runnable_forex_strategies()

        if result.skip_reason and not watch_requirements and not service.registered_demand():
            if result.skip_reason != self._pipeline_idle_reason:
                self._pipeline_idle_reason = result.skip_reason
                self._pipeline_idle_until = when + _PIPELINE_IDLE_RECHECK
                return [], [result.skip_reason]
            self._pipeline_idle_reason = result.skip_reason
            self._pipeline_idle_until = when + _PIPELINE_IDLE_RECHECK
            return [], []

        self._clear_pipeline_idle()

        if result.skip_reason:
            requirements: list[CandleRequirement] = []
        else:
            requirements, warnings = collect_candle_requirements(result.strategies)

        all_requirements = list(requirements) + list(watch_requirements)
        for symbol, timeframe, _source, bar_count in service.registered_demand():
            all_requirements.append(
                CandleRequirement(timeframe=timeframe, pairs=(symbol,), bar_count=bar_count)
            )

        if not all_requirements and not result.strategies:
            return [], warnings

        # (pair, timeframe, bar_count, bootstrap, incremental, fetch_due)
        due_units: list[tuple[str, str, int, bool, bool, bool]] = []

        for requirement in all_requirements:
            next_at = self._next_fetch_at.get(requirement.timeframe)
            if next_at is None:
                next_at = self._schedule_next_fetch(requirement.timeframe, now=when)

            fetch_due = is_candle_fetch_due(when, next_at)
            if not fetch_due:
                continue

            needs_warmup = await requirement_needs_warmup(requirement, service)

            for pair in requirement.pairs:
                due_units.append(
                    (
                        pair,
                        requirement.timeframe,
                        requirement.bar_count,
                        needs_warmup,
                        not needs_warmup,
                        True,
                    )
                )

            self._schedule_next_fetch(requirement.timeframe, now=when)

        if not due_units and result.strategies:
            runtime = get_asset_runtime("forex")
            if runtime is not None:
                work_plan = runtime.build_work_plan(result.strategies)
                for unit in work_plan.units:
                    complete = await service.cache.is_cache_complete_up_to(
                        unit.pair,
                        unit.timeframe,
                        source="oanda",
                    )
                    expected = expected_latest_closed_bar(unit.timeframe, as_of=when)
                    revision_covers = GLOBAL_CANDLE_REVISIONS.covers_expected(
                        unit.pair,
                        unit.timeframe,
                        expected,
                    )
                    if not complete or not revision_covers:
                        due_units.append(
                            (
                                unit.pair,
                                unit.timeframe,
                                unit.bar_count,
                                False,
                                True,
                                False,
                            )
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
        for pair, timeframe, bar_count, bootstrap, incremental, fetch_due in due_units:
            unit = units_by_key.get((pair, timeframe))
            strategies = tuple(unit.strategies) if unit else ()
            if not strategies and not bootstrap:
                continue

            expected = expected_latest_closed_bar(timeframe, as_of=when)
            revision_covers = GLOBAL_CANDLE_REVISIONS.covers_expected(
                pair,
                timeframe,
                expected,
            )
            # Fetch-due jobs must run even when the new bar is not visible yet — the
            # candle only appears after the Data Manager worker fetch step.
            if (
                not fetch_due
                and revision_covers
                and not bootstrap
            ):
                cache_complete = await service.cache.is_cache_complete_up_to(
                    pair,
                    timeframe,
                    source="oanda",
                    as_of=when,
                )
                if cache_complete:
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
        timeframes: set[str] = set()

        for unit in work_plan.units:
            timeframes.add(unit.timeframe)
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
                    incremental=False,
                    bootstrap=needs_bootstrap,
                    catchup=True,
                )
            )

        for timeframe in timeframes:
            self._schedule_next_fetch(timeframe, now=when)

        return jobs
