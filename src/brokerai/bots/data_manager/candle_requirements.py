from __future__ import annotations

from dataclasses import dataclass

from brokerai.integrations.oanda import timeframe_to_granularity
from brokerai.strategies.candles import compute_required_candles, effective_min_candles
from brokerai.strategies.params import normalize_stored_params
from brokerai.strategies.registry import get_preset


@dataclass(frozen=True)
class CandleRequirement:
    timeframe: str
    pairs: tuple[str, ...]
    bar_count: int
    incremental: bool = False


def strategy_timeframe(strategy: dict) -> str | None:
    timeframe = strategy.get("timeframe")
    if timeframe:
        return str(timeframe)
    params = strategy.get("params") or {}
    value = params.get("timeframe")
    return str(value) if value else None


def strategy_params(strategy: dict) -> dict:
    """Return normalized strategy params when a preset is available."""
    params = strategy.get("params") or {}
    preset_id = strategy.get("preset_id")
    if not preset_id or not params:
        return params
    preset = get_preset(str(preset_id))
    if not preset:
        return params
    return normalize_stored_params(preset, params)


def required_candle_bars(strategy: dict, *, maximum: int = 2000) -> int:
    """Estimate how many historical bars a strategy needs (respects stored min_candles)."""
    params = strategy_params(strategy)
    if params:
        return effective_min_candles(params, maximum=maximum)
    return compute_required_candles({}, maximum=maximum)


def collect_candle_requirements(
    strategies: list[tuple[dict, list[str]]],
) -> tuple[list[CandleRequirement], list[str]]:
    """Build one candle request per unique timeframe across runnable forex strategies."""
    merged: dict[str, dict[str, int]] = {}
    warnings: list[str] = []

    for strategy, pairs in strategies:
        timeframe = strategy_timeframe(strategy)
        if not timeframe:
            name = strategy.get("name") or strategy.get("id") or "strategy"
            warnings.append(f"{name} has no timeframe configured")
            continue

        if timeframe_to_granularity(timeframe) is None:
            name = strategy.get("name") or strategy.get("id") or "strategy"
            warnings.append(f"{name}: timeframe {timeframe} is not supported for OANDA candles")
            continue

        bars = required_candle_bars(strategy)
        pair_bars = merged.setdefault(timeframe, {})
        for pair in pairs:
            pair_bars[pair] = max(pair_bars.get(pair, 0), bars)

    requirements = [
        CandleRequirement(
            timeframe=timeframe,
            pairs=tuple(sorted(pair_bars)),
            bar_count=max(pair_bars.values()),
        )
        for timeframe, pair_bars in sorted(merged.items())
    ]
    return requirements, warnings
