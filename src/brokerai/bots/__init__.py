from brokerai.bots.analysis.bot import AnalysisBot
from brokerai.bots.base import Bot
from brokerai.bots.execution.bot import ExecutionBot
from brokerai.bots.research.bot import ResearchBot

BOT_REGISTRY: dict[str, type[Bot]] = {
    "research": ResearchBot,
    "execution": ExecutionBot,
    "analysis": AnalysisBot,
}

__all__ = ["Bot", "BOT_REGISTRY", "ResearchBot", "ExecutionBot", "AnalysisBot"]
