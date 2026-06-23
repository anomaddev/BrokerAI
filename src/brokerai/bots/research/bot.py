import asyncio
import logging

from brokerai.bots.base import Bot

logger = logging.getLogger(__name__)


class ResearchBot(Bot):
    name = "research"

    async def on_start(self) -> None:
        logger.info("Research bot started")

    async def on_stop(self) -> None:
        logger.info("Research bot stopped")

    async def tick(self) -> None:
        logger.debug("Research bot tick")
        await asyncio.sleep(0)
