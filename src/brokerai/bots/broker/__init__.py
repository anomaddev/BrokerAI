__all__ = ["BrokerBot"]


def __getattr__(name: str):
    if name == "BrokerBot":
        from brokerai.bots.broker.bot import BrokerBot

        return BrokerBot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
