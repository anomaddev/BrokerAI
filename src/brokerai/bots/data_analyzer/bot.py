import asyncio
import logging

from brokerai.bots.base import Bot
from brokerai.bots.data_analyzer.sub_analyzer import SubAnalyzer
from brokerai.db.repositories.analysis_results import AnalysisResultsRepository
from brokerai.db.repositories.market_data import MarketDataRepository
from brokerai.db.repositories.research_cache import ResearchCacheRepository

logger = logging.getLogger(__name__)


class DataAnalyzerBot(Bot):
    name = "data_analyzer"

    def __init__(self) -> None:
        super().__init__()
        self._market_repo = MarketDataRepository()
        self._research_repo = ResearchCacheRepository()
        self._results_repo = AnalysisResultsRepository()
        self._sub_analyzers: dict[str, SubAnalyzer] = {}

    async def on_start(self) -> None:
        logger.info("Data Analyzer bot started")

    async def on_stop(self) -> None:
        logger.info("Data Analyzer bot stopped")

    async def tick(self) -> None:
        logger.debug("Data Analyzer tick — would analyze cached data")
        _ = await self._market_repo.find("STUB", "1h", "stub")
        await self._results_repo.insert(
            symbol="STUB",
            analysis_type="stub",
            payload={"status": "alpha_scaffold"},
        )
        if self._sub_analyzers:
            await asyncio.gather(
                *[analyzer.evaluate() for analyzer in self._sub_analyzers.values()],
                return_exceptions=True,
            )
