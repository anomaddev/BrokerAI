from brokerai.bots.base import Bot

BOT_REGISTRY: dict[str, type[Bot]] | None = None


def get_bot_registry() -> dict[str, type[Bot]]:
    global BOT_REGISTRY
    if BOT_REGISTRY is not None:
        return BOT_REGISTRY

    from brokerai.bots.brokers.bot import BrokersBot
    from brokerai.bots.data_analyzer.bot import DataAnalyzerBot
    from brokerai.bots.data_manager.bot import DataManagerBot
    from brokerai.bots.executor.bot import ExecutorBot
    from brokerai.bots.researcher.bot import ResearcherBot

    BOT_REGISTRY = {
        "brokers": BrokersBot,
        "researcher": ResearcherBot,
        "data_manager": DataManagerBot,
        "data_analyzer": DataAnalyzerBot,
        "executor": ExecutorBot,
    }
    return BOT_REGISTRY


__all__ = [
    "Bot",
    "BOT_REGISTRY",
    "get_bot_registry",
]
