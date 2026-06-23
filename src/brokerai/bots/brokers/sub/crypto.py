import logging

from brokerai.bots.brokers.sub.base import SubBroker

logger = logging.getLogger(__name__)


class CryptoSubBroker(SubBroker):
    asset_class = "crypto"

    async def on_start(self) -> None:
        logger.info("Crypto sub-broker ready")

    async def route(self, action: str, payload: dict | None = None) -> None:
        logger.debug("Crypto route: action=%s payload=%s", action, payload)
