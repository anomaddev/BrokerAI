from __future__ import annotations

import logging
from datetime import datetime, timezone

from brokerai.bots.base import Bot
from brokerai.bots.data_manager.service import DataManagerService, set_data_manager_service
from brokerai.bots.researcher.reports import daily_report_exists
from brokerai.bots.researcher.worker import ResearchRequest
from brokerai.bots.researcher.worker_runner import ResearcherWorker
from brokerai.bots.researcher.weekly import (
    completed_debrief_week,
    preview_weekly_brief_skip_reason,
    preview_weekly_debrief_skip_reason,
)
from brokerai.bots.secretary.activity import (
    log_account_summary_updated,
    log_pipeline_batch_completed,
)
from brokerai.bots.secretary.candle_timeline import CandleTimeline
from brokerai.bots.secretary.pipeline import PipelineRunner
from brokerai.bots.secretary.scheduled_research import (
    after_launch_deferral,
    next_brief_probe_at,
    next_brief_schedule_probe_at,
    next_daily_probe_at,
    next_debrief_probe_at,
    next_debrief_schedule_probe_at,
    research_settings_fingerprint,
)
from brokerai.bots.secretary.scheduled_self_backtest import (
    STABLE_UNTIL_SETTINGS as STABLE_UNTIL_BACKTEST_SETTINGS,
    backtest_settings_fingerprint,
    maybe_run_daily_ai_strategy_backtests,
    next_daily_ai_backtest_probe_at,
)
from brokerai.config.settings import get_settings
from brokerai.core.worker_pool import get_worker_pool
from brokerai.db.repositories.backtest_settings import BacktestSettingsRepository
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
        self._research_settings_fp: str | None = None
        self._research_next_check: dict[str, datetime] = {}
        self._backtest_settings_fp: str | None = None
        self._daily_ai_backtest_next_check: datetime | None = None

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
        from brokerai.integrations.oanda_client import close_oanda_client

        await close_oanda_client()
        logger.info("Secretary bot stopped")

    async def status(self) -> dict:
        payload = await super().status()
        avg_ms = (
            int(sum(self._durations_ms) / len(self._durations_ms))
            if self._durations_ms
            else None
        )
        payload.update(
            {
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
        interval = max(60, settings.oanda_account_sync_interval_seconds)
        if self._last_account_fetch_at is not None:
            elapsed = (now - self._last_account_fetch_at).total_seconds()
            if elapsed < interval:
                return

        self._last_account_fetch_at = now
        from brokerai.trading.oanda_account_sync import run_oanda_account_sync

        result = await run_oanda_account_sync()
        if not result.summary_synced or not result.account_id:
            return

        from brokerai.db.repositories.oanda_account_snapshots import OandaAccountSnapshotsRepository

        doc = await OandaAccountSnapshotsRepository().get_latest_summary(
            account_id=result.account_id,
        )
        if doc and self._broker is not None:
            monitor = getattr(self._broker, "_monitor", None)
            if monitor is not None:
                snapshot = OandaAccountSnapshotsRepository.public_summary(doc)
                snapshot["asset_class"] = "forex"
                snapshot["connected"] = True
                monitor.set_account_snapshot("forex", snapshot)
            await log_account_summary_updated("forex")

    def _research_probe_due(self, kind: str, now: datetime) -> bool:
        next_at = self._research_next_check.get(kind)
        return next_at is None or now >= next_at

    def _defer_research_probe(self, kind: str, until: datetime) -> None:
        self._research_next_check[kind] = until
        logger.debug("Secretary — defer %s research probe until %s", kind, until.isoformat())

    async def _maybe_run_scheduled_research(self) -> None:
        if is_research_running():
            return

        now = datetime.now(timezone.utc)
        settings = await ResearchSettingsRepository().get()
        fingerprint = research_settings_fingerprint(settings)
        if fingerprint != self._research_settings_fp:
            self._research_settings_fp = fingerprint
            self._research_next_check.clear()

        pool = get_worker_pool()

        if settings.get("daily_report_enabled", False) and self._research_probe_due("daily", now):
            market_id = settings.get("daily_report_market_id", "london")
            offset = settings.get("daily_report_market_offset_hours", -2)
            if not is_past_scheduled_run(now, market_id, offset):
                self._defer_research_probe(
                    "daily", next_daily_probe_at(now, settings, done_today=False)
                )
            else:
                today = now.date().isoformat()
                daily_done = (
                    settings.get("last_daily_run_date") == today
                    or await daily_report_exists(today)
                )
                if not daily_done:
                    await pool.run(
                        ResearcherWorker,
                        ResearchRequest(scheduled_kind="daily"),
                    )
                    self._defer_research_probe("daily", after_launch_deferral(now))
                else:
                    self._defer_research_probe(
                        "daily", next_daily_probe_at(now, settings, done_today=True)
                    )

        if is_research_running():
            return

        if settings.get("weekly_brief_enabled", False) and self._research_probe_due(
            "weekly_brief", now
        ):
            market_id = settings.get("weekly_brief_market_id", "london")
            offset = settings.get("weekly_brief_market_offset_hours", -1)
            if not is_past_weekly_brief_run(now, market_id, offset):
                self._defer_research_probe(
                    "weekly_brief", next_brief_schedule_probe_at(now, settings)
                )
            else:
                skip = await preview_weekly_brief_skip_reason(settings, now)
                if not skip:
                    await pool.run(
                        ResearcherWorker,
                        ResearchRequest(scheduled_kind="weekly_brief"),
                    )
                self._defer_research_probe(
                    "weekly_brief", next_brief_probe_at(now, settings, skip)
                )

        if is_research_running():
            return

        if settings.get("weekly_debrief_enabled", False) and self._research_probe_due(
            "weekly_debrief", now
        ):
            if completed_debrief_week(now, settings) is None:
                self._defer_research_probe(
                    "weekly_debrief", next_debrief_schedule_probe_at(now, settings)
                )
            else:
                skip = await preview_weekly_debrief_skip_reason(settings, now)
                if not skip:
                    await pool.run(
                        ResearcherWorker,
                        ResearchRequest(scheduled_kind="weekly_debrief"),
                    )
                self._defer_research_probe(
                    "weekly_debrief", next_debrief_probe_at(now, settings, skip)
                )

    async def _maybe_run_daily_ai_strategy_backtests(self) -> None:
        now = datetime.now(timezone.utc)
        settings = await BacktestSettingsRepository().get()
        fingerprint = backtest_settings_fingerprint(settings)
        if fingerprint != self._backtest_settings_fp:
            self._backtest_settings_fp = fingerprint
            self._daily_ai_backtest_next_check = None

        if not settings.get("daily_ai_strategy_backtest_enabled"):
            self._daily_ai_backtest_next_check = STABLE_UNTIL_BACKTEST_SETTINGS
            return

        if (
            self._daily_ai_backtest_next_check is not None
            and now < self._daily_ai_backtest_next_check
        ):
            return

        summary = await maybe_run_daily_ai_strategy_backtests(now=now)
        queued = summary.get("queued") or []
        # Treat any probe as "done for deferral" — skips are idempotent.
        self._daily_ai_backtest_next_check = next_daily_ai_backtest_probe_at(
            now, done_today=bool(queued) or summary.get("reason") != "disabled"
        )

    async def run_startup_pass(self) -> None:
        """Bootstrap candle cache and run initial strategy analysis once at startup."""
        if self._startup_done:
            return

        self._startup_done = True
        startup_jobs = await self._timeline.build_startup_jobs(self._service)
        if startup_jobs:
            logger.info("Secretary startup — %d warm-up pipeline(s)", len(startup_jobs))
            self._queued_jobs = len(startup_jobs)
            self._active_pipelines = len(startup_jobs)
            results = await self._pipeline.run_jobs(startup_jobs)
            await log_pipeline_batch_completed(startup_jobs, results)
            self._record_pipeline_batch(results)
            return
        logger.info("Secretary startup — cache warm, waiting for candle close")

    async def _maybe_drain_learning_jobs(self) -> None:
        """Process at most one queued AI Strategy learning job per tick."""
        try:
            from brokerai.ai_strategy.learning import drain_queued_learning_jobs

            summary = await drain_queued_learning_jobs(limit=1)
            if summary.get("completed") or summary.get("failed"):
                logger.info(
                    "Secretary — learning drain completed=%s failed=%s considered=%s",
                    summary.get("completed"),
                    summary.get("failed"),
                    summary.get("considered"),
                )
        except Exception:
            logger.exception("Secretary — learning job drain failed")

    async def _maybe_drain_ai_strategy_startup_jobs(self) -> None:
        """Advance at most one AI Strategy create-time startup job per tick."""
        try:
            from brokerai.ai_strategy.startup import drain_queued_startup_jobs

            summary = await drain_queued_startup_jobs(limit=1)
            if summary.get("advanced"):
                logger.info(
                    "Secretary — AI startup drain advanced=%s completed=%s failed=%s",
                    summary.get("advanced"),
                    summary.get("completed"),
                    summary.get("failed"),
                )
        except Exception:
            logger.exception("Secretary — AI Strategy startup drain failed")

    async def tick(self) -> None:
        await self._maybe_fetch_account_summary()
        await self._maybe_run_scheduled_research()
        await self._maybe_run_daily_ai_strategy_backtests()
        await self._maybe_drain_learning_jobs()
        await self._maybe_drain_ai_strategy_startup_jobs()

        if not self._startup_done:
            await self.run_startup_pass()
            return

        jobs, warnings = await self._timeline.build_due_jobs(self._service)
        for warning in warnings:
            logger.info("Secretary — %s", warning)

        if not jobs:
            self._queued_jobs = 0
            if warnings:
                return
            logger.debug("Secretary — no pipeline jobs due this tick")
            return

        self._queued_jobs = len(jobs)
        self._max_backlog_seen = max(self._max_backlog_seen, len(jobs))
        self._active_pipelines = len(jobs)
        logger.info("Secretary — running %d pipeline(s)", len(jobs))
        results = await self._pipeline.run_jobs(jobs)
        await log_pipeline_batch_completed(jobs, results)
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
