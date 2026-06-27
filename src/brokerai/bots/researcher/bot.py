from __future__ import annotations

import logging
from datetime import datetime, timezone

from brokerai.bots.base import Bot
from brokerai.bots.researcher.reports import daily_report_exists
from brokerai.db.repositories.research_settings import ResearchSettingsRepository
from brokerai.research_markets import (
    describe_schedule,
    is_past_scheduled_run,
    is_past_weekly_brief_run,
    should_defer_weekly_brief_for_daily,
)
from brokerai.tasks.runner import is_research_running
from brokerai.tasks.research import (
    start_scheduled_daily_task,
    start_scheduled_weekly_brief_task,
    start_scheduled_weekly_debrief_task,
)

logger = logging.getLogger(__name__)

SCHEDULED_DAILY_REPORTS_ENABLED = True


class ResearcherBot(Bot):
    name = "researcher"

    async def on_start(self) -> None:
        if not SCHEDULED_DAILY_REPORTS_ENABLED:
            logger.info("Researcher bot started (scheduled daily reports disabled)")
            return

        settings = await ResearchSettingsRepository().get()
        if settings.get("daily_report_enabled", False):
            logger.info(
                "Researcher bot started (daily report schedule: %s)",
                describe_schedule(
                    settings.get("daily_report_market_id", "london"),
                    settings.get("daily_report_market_offset_hours", -2),
                ),
            )
        else:
            logger.info("Researcher bot started (daily report scheduling enabled, toggle is off)")

    async def on_stop(self) -> None:
        logger.info("Researcher bot stopped")

    async def tick(self) -> None:
        if not SCHEDULED_DAILY_REPORTS_ENABLED:
            return

        if is_research_running():
            return

        now = datetime.now(timezone.utc)
        settings = await ResearchSettingsRepository().get()

        await self._maybe_run_daily(now, settings)
        if is_research_running():
            return

        await self._maybe_run_weekly_brief(now, settings)
        if is_research_running():
            return

        await self._maybe_run_weekly_debrief(now, settings)

    async def _maybe_run_daily(self, now: datetime, settings: dict) -> None:
        if not settings.get("daily_report_enabled", False):
            return

        if not is_past_scheduled_run(
            now,
            settings.get("daily_report_market_id", "london"),
            settings.get("daily_report_market_offset_hours", -2),
        ):
            return

        today = now.date().isoformat()
        if settings.get("last_daily_run_date") == today:
            return

        logger.info("Starting scheduled daily research report")
        task_id, error = await start_scheduled_daily_task()
        if error:
            logger.debug("Scheduled daily report not started: %s", error)
        elif task_id:
            logger.info("Scheduled daily report task started: %s", task_id)

    async def _maybe_run_weekly_brief(self, now: datetime, settings: dict) -> None:
        if not settings.get("weekly_brief_enabled", False):
            return

        if not is_past_weekly_brief_run(
            now,
            settings.get("weekly_brief_market_id", "london"),
            settings.get("weekly_brief_market_offset_hours", -1),
        ):
            return

        today = now.date().isoformat()
        daily_completed = (
            settings.get("last_daily_run_date") == today or daily_report_exists(today)
        )
        if should_defer_weekly_brief_for_daily(
            now,
            daily_report_enabled=bool(settings.get("daily_report_enabled", False)),
            daily_market_id=settings.get("daily_report_market_id", "london"),
            daily_offset_hours=settings.get("daily_report_market_offset_hours", -2),
            brief_market_id=settings.get("weekly_brief_market_id", "london"),
            brief_offset_hours=settings.get("weekly_brief_market_offset_hours", -1),
            daily_completed_today=daily_completed,
        ):
            logger.debug(
                "Deferring weekly brief until today's daily report completes (same or later schedule)"
            )
            return

        logger.info("Starting scheduled weekly brief")
        task_id, error = await start_scheduled_weekly_brief_task()
        if error:
            logger.debug("Scheduled weekly brief not started: %s", error)
        elif task_id:
            logger.info("Scheduled weekly brief task started: %s", task_id)

    async def _maybe_run_weekly_debrief(self, now: datetime, settings: dict) -> None:
        if not settings.get("weekly_debrief_enabled", False):
            return

        logger.info("Checking scheduled weekly debrief")
        task_id, error = await start_scheduled_weekly_debrief_task()
        if error:
            logger.debug("Scheduled weekly debrief not started: %s", error)
        elif task_id:
            logger.info("Scheduled weekly debrief task started: %s", task_id)
