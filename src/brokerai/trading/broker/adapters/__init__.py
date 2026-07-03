from brokerai.trading.broker.adapters.base import get_adapter, register_adapter
from brokerai.trading.broker.adapters.oanda import OandaAdapter

register_adapter(OandaAdapter())

__all__ = ["OandaAdapter", "get_adapter", "register_adapter"]
