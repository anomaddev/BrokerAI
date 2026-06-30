from __future__ import annotations

import logging

from brokerai.bots.base import EphemeralBot, WorkerResult
from brokerai.bots.researcher.worker import ResearchMode, ResearchRequest
from brokerai.tasks.research import (
    start_scheduled_daily_task,
    start_scheduled_weekly_brief_task,
    start_scheduled_weekly_debrief_task,
)

logger = logging.getLogger(__name__)


class ResearcherWorker(EphemeralBot[ResearchRequest, str]):
    """On-demand research worker; long-running work delegates to tasks/runner."""

    name = "researcher_worker"
    asset_class = "multi"

    async def run(self, request: ResearchRequest) -> WorkerResult[str]:
        if request.mode == ResearchMode.TRADE_ANALYSIS:
            # TODO(loop): implement trade_analysis via connected AI models
            return WorkerResult(
                ok=False,
                error="trade_analysis mode not implemented",
            )

        task_id: str | None = None
        error: str | None = None

        if request.scheduled_kind == "daily":
            task_id, error = await start_scheduled_daily_task()
        elif request.scheduled_kind == "weekly_brief":
            task_id, error = await start_scheduled_weekly_brief_task()
        elif request.scheduled_kind == "weekly_debrief":
            task_id, error = await start_scheduled_weekly_debrief_task()
        else:
            return WorkerResult(
                ok=False,
                error="On-demand research requires scheduled_kind or web API integration",
            )

        if error:
            return WorkerResult(ok=False, error=error)
        if not task_id:
            return WorkerResult(ok=False, error="Research task not started")

        logger.info("Researcher worker started task %s (%s)", task_id, request.scheduled_kind)
        return WorkerResult(ok=True, data=task_id)
