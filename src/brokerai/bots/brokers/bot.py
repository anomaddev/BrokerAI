from __future__ import annotations

from typing import TYPE_CHECKING

from brokerai.bots.base import Bot
from brokerai.bots.brokers.sub.crypto import CryptoSubBroker
from brokerai.bots.brokers.sub.forex import ForexSubBroker
from brokerai.bots.brokers.sub.futures import FuturesSubBroker
from brokerai.bots.brokers.sub.metals import MetalsSubBroker
from brokerai.bots.brokers.sub.options import OptionsSubBroker
from brokerai.bots.brokers.sub.stocks import StocksSubBroker

if TYPE_CHECKING:
    from brokerai.bots.executor.bot import ExecutorBot

logger = __import__("logging").getLogger(__name__)


class BrokersBot(Bot):
    name = "brokers"

    def __init__(self) -> None:
        super().__init__()
        self._sub_brokers = {
            "crypto": CryptoSubBroker(),
            "forex": ForexSubBroker(),
            "metals": MetalsSubBroker(),
            "stocks": StocksSubBroker(),
            "futures": FuturesSubBroker(),
            "options": OptionsSubBroker(),
        }
        self._executor: ExecutorBot | None = None

    def attach_executor(self, bot: ExecutorBot) -> None:
        self._executor = bot

    async def on_start(self) -> None:
        logger.info("Brokers bot started")
        for sub in self._sub_brokers.values():
            await sub.on_start()

    async def on_stop(self) -> None:
        logger.info("Brokers bot stopped")

    async def tick(self) -> None:
        if self._executor is None:
            logger.debug("Brokers bot tick — no executor attached")
            return

        intents = self._executor.consume_pending_intents()
        if not intents:
            logger.debug("Brokers bot tick — no pending intents")
            return

        from dataclasses import asdict

        for intent in intents:
            await self.route(intent.asset_class, "place_order", asdict(intent))

    async def route(self, asset_class: str, action: str, payload: dict | None = None) -> None:
        sub = self._sub_brokers.get(asset_class)
        if sub is None:
            logger.warning("Unknown asset class: %s", asset_class)
            return
        logger.info("Routing %s action=%s", asset_class, action)
        await sub.route(action, payload)
