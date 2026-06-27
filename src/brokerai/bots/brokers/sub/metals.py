import logging

from brokerai.bots.brokers.sub.base import SubBroker

logger = logging.getLogger(__name__)


class MetalsSubBroker(SubBroker):
    asset_class = "metals"

    async def on_start(self) -> None:
        logger.info("Precious metals sub-broker ready")

    async def route(self, action: str, payload: dict | None = None) -> None:
        logger.debug("Precious metals route: action=%s payload=%s", action, payload)
