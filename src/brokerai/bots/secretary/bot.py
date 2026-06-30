from __future__ import annotations

import logging
from datetime import datetime, timezone

from brokerai.bots.base import Bot
from brokerai.bots.data_manager.service import DataManagerService, set_data_manager_service
from brokerai.bots.researcher.worker import ResearchRequest
from brokerai.bots.researcher.worker_runner import ResearcherWorker
from brokerai.bots.researcher.weekly import (
    completed_debrief_week,
    preview_weekly_brief_skip_reason,
    preview_weekly_debrief_skip_reason,
)
from brokerai.bots.secretary.activity import log_account_summary_updated
from brokerai.bots.secretary.candle_timeline import CandleTimeline
from brokerai.bots.secretary.pipeline import PipelineRunner
from brokerai.bots.data_manager.worker import AccountSummaryRequest, fetch_account_summary
from brokerai.config.settings import get_settings
from brokerai.core.worker_pool import get_worker_pool
from brokerai.db.repositories.research_settings import ResearchSettingsRepository
from brokerai.research_markets import is_past_scheduled_run, is_past_weekly_brief_run
from brokerai.tasks.runner import is_research_running

logger = logging.getLogger(__name__)


class SecretaryBot(Bot):
    """Persistent task coordinator: candle timeline, pipeline dispatch, timed events."""

    name = "secretary"

    def __init__(self) -> None:
        super().__init__()
        self._service = DataManagerService()
        self._timeline = CandleTimeline()
        self._pipeline = PipelineRunner()
        self._broker: object | None = None
        self._startup_done = False
        self._queued_jobs = 0
        self._active_pipelines = 0
        self._last_completed_at: datetime | None = None
        self._max_backlog_seen = 0
        self._durations_ms: list[int] = []
        self._last_account_fetch_at: datetime | None = None

    @property
    def service(self) -> DataManagerService:
        return self._service

    def attach_broker(self, broker: object) -> None:
        self._broker = broker
        self._pipeline.attach_broker(broker)

    async def on_start(self) -> None:
        set_data_manager_service(self._service)
        logger.info("Secretary bot started")

    async def on_stop(self) -> None:
        set_data_manager_service(None)
        logger.info("Secretary bot stopped")

    async def status(self) -> dict:
        payload = await super().status()
        settings = get_settings()
        avg_ms = (
            int(sum(self._durations_ms) / len(self._durations_ms))
            if self._durations_ms
            else None
        )
        payload.update(
            {
                "use_secretary_pipeline": settings.use_secretary_pipeline,
                "queued_jobs": self._queued_jobs,
                "active_pipelines": self._active_pipelines,
                "last_completed_at": (
                    self._last_completed_at.isoformat() if self._last_completed_at else None
                ),
                "max_backlog_seen": self._max_backlog_seen,
                "avg_pipeline_duration_ms": avg_ms,
                "next_candle_fetches": self._timeline.snapshot_next_fetches(),
                "worker_pool": get_worker_pool().status(),
            }
        )
        return payload

    async def _maybe_fetch_account_summary(self) -> None:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        interval = settings.broker_sync_interval_seconds
        if self._last_account_fetch_at is not None:
            elapsed = (now - self._last_account_fetch_at).total_seconds()
            if elapsed < interval:
                return

        self._last_account_fetch_at = now
        result = await fetch_account_summary(AccountSummaryRequest(asset_class="forex"))
        if result.ok and result.data and self._broker is not None:
            monitor = getattr(self._broker, "_monitor", None)
            if monitor is not None:
                monitor.set_account_snapshot("forex", result.data)
            await log_account_summary_updated("forex")

    async def _maybe_run_scheduled_research(self) -> None:
        if is_research_running():
            return

        now = datetime.now(timezone.utc)
        settings = await ResearchSettingsRepository().get()
        pool = get_worker_pool()

        if settings.get("daily_report_enabled", False):
            if is_past_scheduled_run(
                now,
                settings.get("daily_report_market_id", "london"),
                settings.get("daily_report_market_offset_hours", -2),
            ):
                today = now.date().isoformat()
                if settings.get("last_daily_run_date") != today:
                    await pool.run(
                        ResearcherWorker,
                        ResearchRequest(scheduled_kind="daily"),
                    )

        if is_research_running():
            return

        if settings.get("weekly_brief_enabled", False):
            if is_past_weekly_brief_run(
                now,
                settings.get("weekly_brief_market_id", "london"),
                settings.get("weekly_brief_market_offset_hours", -1),
            ):
                skip = await preview_weekly_brief_skip_reason(settings, now)
                if not skip:
                    await pool.run(
                        ResearcherWorker,
                        ResearchRequest(scheduled_kind="weekly_brief"),
                    )

        if is_research_running():
            return

        if settings.get("weekly_debrief_enabled", False):
            if completed_debrief_week(now, settings) is not None:
                skip = await preview_weekly_debrief_skip_reason(settings, now)
                if not skip:
                    await pool.run(
                        ResearcherWorker,
                        ResearchRequest(scheduled_kind="weekly_debrief"),
                    )

    async def tick(self) -> None:
        settings = get_settings()
        await self._maybe_fetch_account_summary()
        await self._maybe_run_scheduled_research()

        if not settings.use_secretary_pipeline:
            jobs, warnings = await self._timeline.build_due_jobs(self._service)
            for warning in warnings:
                logger.debug("Secretary schedule-only — %s", warning)
            if jobs:
                logger.info(
                    "Secretary schedule-only — would run %d pipeline(s)",
                    len(jobs),
                )
            return

        if not self._startup_done:
            startup_jobs = await self._timeline.build_startup_jobs(self._service)
            self._startup_done = True
            if startup_jobs:
                logger.info("Secretary startup — %d warm-up pipeline(s)", len(startup_jobs))
                self._queued_jobs = len(startup_jobs)
                self._active_pipelines = len(startup_jobs)
                results = await self._pipeline.run_jobs(startup_jobs)
                self._record_pipeline_batch(results)
                return

        jobs, warnings = await self._timeline.build_due_jobs(self._service)
        for warning in warnings:
            logger.debug("Secretary — %s", warning)

        if not jobs:
            self._queued_jobs = 0
            return

        self._queued_jobs = len(jobs)
        self._max_backlog_seen = max(self._max_backlog_seen, len(jobs))
        self._active_pipelines = len(jobs)
        logger.info("Secretary — running %d pipeline(s)", len(jobs))
        results = await self._pipeline.run_jobs(jobs)
        self._record_pipeline_batch(results)

    def _record_pipeline_batch(self, results: list) -> None:
        self._active_pipelines = 0
        self._queued_jobs = 0
        self._last_completed_at = datetime.now(timezone.utc)
        for result in results:
            if result.duration_ms:
                self._durations_ms.append(result.duration_ms)
                if len(self._durations_ms) > 100:
                    self._durations_ms = self._durations_ms[-100:]
