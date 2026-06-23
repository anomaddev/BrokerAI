import logging
from datetime import date

from brokerai.bots.base import Bot
from brokerai.db.repositories.research_cache import ResearchCacheRepository

logger = logging.getLogger(__name__)


class ResearcherBot(Bot):
    name = "researcher"

    def __init__(self) -> None:
        super().__init__()
        self._repo = ResearchCacheRepository()

    async def on_start(self) -> None:
        logger.info("Researcher bot started (pre-market run scheduled — stub)")

    async def on_stop(self) -> None:
        logger.info("Researcher bot stopped")

    async def tick(self) -> None:
        logger.debug("Researcher tick — would gather daily research")
        today = date.today().isoformat()
        await self._repo.upsert(
            date=today,
            category="stub",
            summary="Alpha stub — no live news gathering yet",
            sources=[],
        )
