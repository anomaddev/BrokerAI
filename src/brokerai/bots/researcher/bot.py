from __future__ import annotations

import logging
from datetime import datetime, timezone

from brokerai.bots.base import Bot
from brokerai.bots.researcher.runner import run_daily_report
from brokerai.db.repositories.research_settings import ResearchSettingsRepository
from brokerai.research_markets import describe_schedule, is_past_scheduled_run

logger = logging.getLogger(__name__)

SCHEDULED_DAILY_REPORTS_ENABLED = True


class ResearcherBot(Bot):
    name = "researcher"

    def __init__(self) -> None:
        super().__init__()
        self._running_report = False

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

        if self._running_report:
            return

        now = datetime.now(timezone.utc)
        settings = await ResearchSettingsRepository().get()
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

        self._running_report = True
        try:
            logger.info("Starting scheduled daily research report")
            result = await run_daily_report(force=False)
            if result.ok:
                if result.report_path:
                    logger.info(
                        "Daily report complete: %s (groups: %s)",
                        result.report_path,
                        ", ".join(result.groups_processed),
                    )
                elif result.skipped_reason:
                    logger.info("Daily report skipped: %s", result.skipped_reason)
            elif result.skipped_reason:
                logger.debug("Daily report skipped: %s", result.skipped_reason)
            else:
                logger.warning("Daily report failed: %s", "; ".join(result.errors))
        except Exception:
            logger.exception("Daily report crashed")
        finally:
            self._running_report = False
