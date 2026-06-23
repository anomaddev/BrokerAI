import logging

from brokerai.bots.base import Bot
from brokerai.bots.brokers.sub.crypto import CryptoSubBroker
from brokerai.bots.brokers.sub.forex import ForexSubBroker
from brokerai.bots.brokers.sub.futures import FuturesSubBroker
from brokerai.bots.brokers.sub.options import OptionsSubBroker
from brokerai.bots.brokers.sub.stocks import StocksSubBroker

logger = logging.getLogger(__name__)


class BrokersBot(Bot):
    name = "brokers"

    def __init__(self) -> None:
        super().__init__()
        self._sub_brokers = {
            "crypto": CryptoSubBroker(),
            "forex": ForexSubBroker(),
            "stocks": StocksSubBroker(),
            "futures": FuturesSubBroker(),
            "options": OptionsSubBroker(),
        }

    async def on_start(self) -> None:
        logger.info("Brokers bot started")
        for sub in self._sub_brokers.values():
            await sub.on_start()

    async def on_stop(self) -> None:
        logger.info("Brokers bot stopped")

    async def tick(self) -> None:
        logger.debug("Brokers bot tick")

    async def route(self, asset_class: str, action: str, payload: dict | None = None) -> None:
        sub = self._sub_brokers.get(asset_class)
        if sub is None:
            logger.warning("Unknown asset class: %s", asset_class)
            return
        logger.info("Routing %s action=%s", asset_class, action)
        await sub.route(action, payload)
