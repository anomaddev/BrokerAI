from __future__ import annotations

import logging
import time

from brokerai.bots.data_analyzer.assets import run_asset_analyst
from brokerai.bots.data_manager.assets import run_asset_data_manager
from brokerai.bots.researcher.concurrency import gather_limited
from brokerai.bots.secretary import activity as pipeline_activity
from brokerai.bots.secretary.types import CandleJob, FetchStatus, PipelineContext, PipelineResult
from brokerai.config.settings import get_settings
from brokerai.core.worker_pool import get_worker_pool
from brokerai.trading.candle_revision import GLOBAL_CANDLE_REVISIONS

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Runs Manager → Analyst → Broker for one or more CandleJobs."""

    def __init__(self, broker: object | None = None) -> None:
        self._broker = broker

    def attach_broker(self, broker: object) -> None:
        self._broker = broker

    async def run_job(self, job: CandleJob) -> PipelineResult:
        context = PipelineContext.from_job(job)
        started = time.monotonic()
        pool = get_worker_pool()

        try:
            await pipeline_activity.log_pipeline_scheduled(context)

            fetch_start = time.monotonic()
            await pipeline_activity.log_pipeline_fetch_started(context)
            fetch_result = await run_asset_data_manager(context)
            if not fetch_result.ok or fetch_result.data is None:
                error = fetch_result.error or "Data Manager worker failed"
                await pipeline_activity.log_pipeline_failed(context, "fetch", error)
                return PipelineResult(
                    job_id=job.job_id,
                    ok=False,
                    error=error,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )

            context = fetch_result.data
            await pipeline_activity.log_pipeline_fetch_completed(
                context,
                int((time.monotonic() - fetch_start) * 1000),
            )

            if context.fetch_status == FetchStatus.ERROR:
                await pipeline_activity.log_pipeline_failed(
                    context,
                    "fetch",
                    "Fetch returned error status",
                )
                return PipelineResult(
                    job_id=job.job_id,
                    ok=False,
                    error="fetch error",
                    duration_ms=int((time.monotonic() - started) * 1000),
                )

            if not context.strategies:
                logger.info(
                    "Pipeline — fetch complete for %s %s, no strategies to analyze",
                    context.symbol,
                    context.timeframe,
                )
                duration_ms = int((time.monotonic() - started) * 1000)
                return PipelineResult(job_id=job.job_id, ok=True, duration_ms=duration_ms)

            if (
                not context.bootstrap
                and context.latest_candle_time
                and not GLOBAL_CANDLE_REVISIONS.has_changed(
                    context.symbol,
                    context.timeframe,
                    context.latest_candle_time,
                )
            ):
                logger.info(
                    "Pipeline — skipping analysis for %s %s (candle %s already analyzed)",
                    context.symbol,
                    context.timeframe,
                    context.latest_candle_time,
                )
                duration_ms = int((time.monotonic() - started) * 1000)
                return PipelineResult(job_id=job.job_id, ok=True, duration_ms=duration_ms)

            analyze_start = time.monotonic()
            await pipeline_activity.log_pipeline_analyze_started(context)
            analyze_result = await run_asset_analyst(context)
            if not analyze_result.ok or analyze_result.data is None:
                error = analyze_result.error or "Analyst worker failed"
                await pipeline_activity.log_pipeline_failed(context, "analyze", error)
                return PipelineResult(
                    job_id=job.job_id,
                    ok=False,
                    error=error,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )

            analyses = analyze_result.data
            await pipeline_activity.log_pipeline_analyze_completed(
                context,
                int((time.monotonic() - analyze_start) * 1000),
                result_count=len(analyses),
            )

            if context.latest_candle_time:
                GLOBAL_CANDLE_REVISIONS.mark_updated(
                    context.symbol,
                    context.timeframe,
                    context.latest_candle_time,
                )

            if self._broker is not None and hasattr(self._broker, "process_analysis"):
                await self._broker.process_analysis(analyses, context)

            duration_ms = int((time.monotonic() - started) * 1000)
            return PipelineResult(
                job_id=job.job_id,
                ok=True,
                analyses=analyses,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            logger.exception("Pipeline failed for %s", job.job_id)
            await pipeline_activity.log_pipeline_failed(context, "pipeline", str(exc))
            return PipelineResult(
                job_id=job.job_id,
                ok=False,
                error=str(exc),
                duration_ms=int((time.monotonic() - started) * 1000),
            )

    async def run_jobs(self, jobs: list[CandleJob]) -> list[PipelineResult]:
        if not jobs:
            return []

        settings = get_settings()
        limit = settings.pipeline_concurrency

        async def _run(job: CandleJob) -> PipelineResult:
            return await self.run_job(job)

        return await gather_limited(
            [_run(job) for job in jobs],
            limit=limit,
        )
