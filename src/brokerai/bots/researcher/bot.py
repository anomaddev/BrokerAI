import logging
from datetime import date, datetime, timezone

from brokerai.bots.base import Bot
from brokerai.bots.researcher.runner import run_daily_report
from brokerai.db.repositories.research_settings import ResearchSettingsRepository

logger = logging.getLogger(__name__)

DAILY_RUN_HOUR_UTC = 6


class ResearcherBot(Bot):
    name = "researcher"

    def __init__(self) -> None:
        super().__init__()
        self._running_report = False

    async def on_start(self) -> None:
        logger.info("Researcher bot started (daily report scheduled for %02d:00 UTC)", DAILY_RUN_HOUR_UTC)

    async def on_stop(self) -> None:
        logger.info("Researcher bot stopped")

    async def tick(self) -> None:
        if self._running_report:
            return

        now = datetime.now(timezone.utc)
        if now.hour < DAILY_RUN_HOUR_UTC:
            return

        today = date.today().isoformat()
        settings = await ResearchSettingsRepository().get()
        if settings.get("last_daily_run_date") == today:
            return

        self._running_report = True
        try:
            logger.info("Starting scheduled daily research report")
            result = await run_daily_report(force=False)
            if result.ok:
                logger.info(
                    "Daily report complete: %s (groups: %s)",
                    result.report_path,
                    ", ".join(result.groups_processed),
                )
            elif result.skipped_reason:
                logger.debug("Daily report skipped: %s", result.skipped_reason)
            else:
                logger.warning("Daily report failed: %s", "; ".join(result.errors))
        except Exception:
            logger.exception("Daily report crashed")
        finally:
            self._running_report = False
