import asyncio
import logging

from brokerai.bots.base import Bot

logger = logging.getLogger(__name__)


class AnalysisBot(Bot):
    name = "analysis"

    async def on_start(self) -> None:
        logger.info("Analysis bot started")

    async def on_stop(self) -> None:
        logger.info("Analysis bot stopped")

    async def tick(self) -> None:
        logger.debug("Analysis bot tick")
        await asyncio.sleep(0)
