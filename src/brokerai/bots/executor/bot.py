import logging

from brokerai.bots.base import Bot

logger = logging.getLogger(__name__)


class ExecutorBot(Bot):
    name = "executor"

    async def on_start(self) -> None:
        logger.info("Executor bot started")

    async def on_stop(self) -> None:
        logger.info("Executor bot stopped")

    async def tick(self) -> None:
        logger.debug("Executor tick — would execute trade actions when requested")
