from __future__ import annotations

import logging

from brokerai.bots.base import Bot
from brokerai.db.repositories.research_settings import ResearchSettingsRepository
from brokerai.research_markets import describe_schedule

logger = logging.getLogger(__name__)


class ResearcherBot(Bot):
    """Research worker host; scheduled reports are dispatched by the Secretary bot."""

    name = "researcher"

    async def on_start(self) -> None:
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
            logger.info("Researcher bot started")

    async def on_stop(self) -> None:
        logger.info("Researcher bot stopped")

    async def tick(self) -> None:
        """No-op — Secretary dispatches research workers on schedule."""
