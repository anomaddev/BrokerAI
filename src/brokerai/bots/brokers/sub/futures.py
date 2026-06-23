import logging

from brokerai.bots.brokers.sub.base import SubBroker

logger = logging.getLogger(__name__)


class FuturesSubBroker(SubBroker):
    asset_class = "futures"

    async def on_start(self) -> None:
        logger.info("Futures sub-broker ready")

    async def route(self, action: str, payload: dict | None = None) -> None:
        logger.debug("Futures route: action=%s payload=%s", action, payload)
