from __future__ import annotations

from brokerai.bots.data_manager.candle_requirements import (
    required_candle_bars,
    strategy_timeframe,
)
from brokerai.trading.types import WorkPlan, WorkUnit


def build_work_plan(
    strategies: list[tuple[dict, list[str]]],
    *,
    asset_class: str = "forex",
) -> WorkPlan:
    """Flatten enabled strategies × pairs into grouped work units by (timeframe, pair)."""
    grouped: dict[tuple[str, str], dict] = {}

    for strategy, pairs in strategies:
        timeframe = strategy_timeframe(strategy)
        if not timeframe:
            continue

        bars = required_candle_bars(strategy)
        for pair in pairs:
            key = (timeframe, pair)
            bucket = grouped.setdefault(
                key,
                {"bar_count": 0, "strategies": []},
            )
            bucket["bar_count"] = max(bucket["bar_count"], bars)
            if strategy not in bucket["strategies"]:
                bucket["strategies"].append(strategy)

    units = [
        WorkUnit(
            pair=pair,
            asset_class=asset_class,
            timeframe=timeframe,
            bar_count=bucket["bar_count"],
            strategies=tuple(bucket["strategies"]),
        )
        for (timeframe, pair), bucket in sorted(grouped.items())
    ]
    timeframes = tuple(sorted({unit.timeframe for unit in units}))
    return WorkPlan(units=tuple(units), timeframes=timeframes)
