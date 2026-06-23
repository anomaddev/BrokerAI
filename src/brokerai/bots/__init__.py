from brokerai.bots.base import Bot
from brokerai.bots.brokers.bot import BrokersBot
from brokerai.bots.data_analyzer.bot import DataAnalyzerBot
from brokerai.bots.data_manager.bot import DataManagerBot
from brokerai.bots.executor.bot import ExecutorBot
from brokerai.bots.researcher.bot import ResearcherBot

BOT_REGISTRY: dict[str, type[Bot]] = {
    "brokers": BrokersBot,
    "researcher": ResearcherBot,
    "data_manager": DataManagerBot,
    "data_analyzer": DataAnalyzerBot,
    "executor": ExecutorBot,
}

__all__ = [
    "Bot",
    "BOT_REGISTRY",
    "BrokersBot",
    "ResearcherBot",
    "DataManagerBot",
    "DataAnalyzerBot",
    "ExecutorBot",
]
