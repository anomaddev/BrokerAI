import logging

from brokerai.bots.brokers.sub.base import SubBroker

logger = logging.getLogger(__name__)


class ForexSubBroker(SubBroker):
    asset_class = "forex"

    async def on_start(self) -> None:
        logger.info("Forex sub-broker ready")

    async def route(self, action: str, payload: dict | None = None) -> None:
        logger.debug("Forex route: action=%s payload=%s", action, payload)
