import logging

from brokerai.bots.brokers.sub.base import SubBroker

logger = logging.getLogger(__name__)


class OptionsSubBroker(SubBroker):
    asset_class = "options"

    async def on_start(self) -> None:
        logger.info("Options sub-broker ready")

    async def route(self, action: str, payload: dict | None = None) -> None:
        logger.debug("Options route: action=%s payload=%s", action, payload)
