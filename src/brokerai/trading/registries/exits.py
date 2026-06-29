from __future__ import annotations

from typing import Any, Protocol

from brokerai.trading.indicator_cache import IndicatorCacheView
from brokerai.trading.types import ExitIntent


class ExitMonitor(Protocol):
    exit_mode: str

    async def evaluate(
        self,
        trade: dict[str, Any],
        candles: list[dict[str, Any]],
        params: dict[str, Any],
        indicators: IndicatorCacheView,
    ) -> ExitIntent | None: ...


class ExitMonitorFactory(Protocol):
    def supports(self, trade: dict[str, Any], params: dict[str, Any]) -> bool: ...

    def create(self, trade: dict[str, Any], params: dict[str, Any]) -> ExitMonitor: ...


_FACTORIES: list[ExitMonitorFactory] = []


def register_exit_factory(factory: ExitMonitorFactory) -> None:
    _FACTORIES.append(factory)


def create_exit_monitor(trade: dict[str, Any], params: dict[str, Any]) -> ExitMonitor | None:
    for factory in _FACTORIES:
        if factory.supports(trade, params):
            return factory.create(trade, params)
    return None
