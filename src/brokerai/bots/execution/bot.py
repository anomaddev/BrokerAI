import asyncio
import logging

from brokerai.bots.base import Bot

logger = logging.getLogger(__name__)


class ExecutionBot(Bot):
    name = "execution"

    async def on_start(self) -> None:
        logger.info("Execution bot started")

    async def on_stop(self) -> None:
        logger.info("Execution bot stopped")

    async def tick(self) -> None:
        logger.debug("Execution bot tick")
        await asyncio.sleep(0)
