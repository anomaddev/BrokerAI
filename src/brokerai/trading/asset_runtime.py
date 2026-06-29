from __future__ import annotations

from typing import Protocol

from brokerai.bots.data_manager.forex_strategies import ForexStrategyLoadResult, load_runnable_forex_strategies
from brokerai.trading.types import WorkPlan
from brokerai.trading.work_plan import build_work_plan


class StrategyLoadResult(Protocol):
    strategies: list[tuple[dict, list[str]]]
    skip_reason: str | None


class AssetRuntime(Protocol):
    asset_class: str

    async def load_runnable_strategies(self) -> StrategyLoadResult: ...

    def build_work_plan(self, strategies: list[tuple[dict, list[str]]]) -> WorkPlan: ...


class ForexRuntime:
    asset_class = "forex"

    async def load_runnable_strategies(self) -> ForexStrategyLoadResult:
        return await load_runnable_forex_strategies()

    def build_work_plan(self, strategies: list[tuple[dict, list[str]]]) -> WorkPlan:
        return build_work_plan(strategies, asset_class=self.asset_class)


_RUNTIMES: dict[str, AssetRuntime] = {
    "forex": ForexRuntime(),
}


def get_asset_runtime(asset_class: str) -> AssetRuntime | None:
    return _RUNTIMES.get(asset_class)


def register_asset_runtime(runtime: AssetRuntime) -> None:
    _RUNTIMES[runtime.asset_class] = runtime


async def load_all_runnable_strategies() -> list[tuple[dict, list[str], str]]:
    combined: list[tuple[dict, list[str], str]] = []
    for asset_class, runtime in _RUNTIMES.items():
        result = await runtime.load_runnable_strategies()
        if result.skip_reason:
            continue
        for strategy, pairs in result.strategies:
            combined.append((strategy, pairs, asset_class))
    return combined
