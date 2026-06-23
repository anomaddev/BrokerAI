import logging

from brokerai.bots.base import Bot
from brokerai.db.repositories.market_data import MarketDataRepository

logger = logging.getLogger(__name__)


class DataManagerBot(Bot):
    name = "data_manager"

    def __init__(self) -> None:
        super().__init__()
        self._repo = MarketDataRepository()

    async def on_start(self) -> None:
        logger.info("Data Manager bot started")

    async def on_stop(self) -> None:
        logger.info("Data Manager bot stopped")

    async def tick(self) -> None:
        logger.debug("Data Manager tick — would fetch market data")
        await self._repo.upsert(
            symbol="STUB",
            timeframe="1h",
            source="stub",
            data=[],
        )
