import logging

from brokerai.bots.brokers.sub.base import SubBroker

logger = logging.getLogger(__name__)


class StocksSubBroker(SubBroker):
    asset_class = "stocks"

    async def on_start(self) -> None:
        logger.info("Stocks sub-broker ready")

    async def route(self, action: str, payload: dict | None = None) -> None:
        logger.debug("Stocks route: action=%s payload=%s", action, payload)
