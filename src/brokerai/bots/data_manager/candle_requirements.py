from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brokerai.integrations.oanda import timeframe_to_granularity
from brokerai.strategies.candles import compute_required_candles, effective_min_candles
from brokerai.strategies.params import normalize_stored_params
from brokerai.strategies.registry import get_preset
from brokerai.trading.presets.ema_crossover.htf_bias import (
    htf_bias_filter_spec,
    signal_ema_periods,
)


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


def strategy_extra_timeframes(params: dict[str, Any]) -> list[str]:
    """Return extra candle timeframes needed beyond the primary strategy TF.

    Includes ``additional_timeframes`` and an enabled ``htf_bias`` filter timeframe.
    """
    needed: list[str] = []
    seen: set[str] = set()

    def _add(raw: Any) -> None:
        tf = str(raw or "").strip()
        if not tf or tf in seen:
            return
        seen.add(tf)
        needed.append(tf)

    for item in params.get("additional_timeframes") or []:
        _add(item)

    htf = htf_bias_filter_spec(params)
    if htf is not None:
        _add(htf.get("timeframe") or "H4")

    return needed


def htf_required_bars(params: dict[str, Any], *, maximum: int = 2000) -> int:
    """Bars needed to warm HTF EMAs for bias / extra-timeframe analysis."""
    _fast, slow = signal_ema_periods(params)
    return min(maximum, max(int(slow) * 3, 63))


def _merge_pair_bars(
    merged: dict[str, dict[str, int]],
    *,
    timeframe: str,
    pairs: list[str],
    bars: int,
) -> None:
    pair_bars = merged.setdefault(timeframe, {})
    for pair in pairs:
        pair_bars[pair] = max(pair_bars.get(pair, 0), bars)


def collect_candle_requirements(
    strategies: list[tuple[dict, list[str]]],
) -> tuple[list[CandleRequirement], list[str]]:
    """Build one candle request per unique timeframe across runnable forex strategies.

    Also schedules ``additional_timeframes`` and enabled ``htf_bias`` timeframes so
    higher-timeframe filters can warm from the shared candle cache.
    """
    merged: dict[str, dict[str, int]] = {}
    warnings: list[str] = []

    for strategy, pairs in strategies:
        name = strategy.get("name") or strategy.get("id") or "strategy"
        timeframe = strategy_timeframe(strategy)
        if not timeframe:
            warnings.append(f"{name} has no timeframe configured")
            continue

        if timeframe_to_granularity(timeframe) is None:
            warnings.append(f"{name}: timeframe {timeframe} is not supported for OANDA candles")
            continue

        bars = required_candle_bars(strategy)
        _merge_pair_bars(merged, timeframe=timeframe, pairs=pairs, bars=bars)

        params = strategy_params(strategy)
        extra_bars = htf_required_bars(params)
        for extra_tf in strategy_extra_timeframes(params):
            if extra_tf == timeframe:
                continue
            if timeframe_to_granularity(extra_tf) is None:
                warnings.append(
                    f"{name}: additional timeframe {extra_tf} is not supported for OANDA candles"
                )
                continue
            _merge_pair_bars(merged, timeframe=extra_tf, pairs=pairs, bars=extra_bars)

    requirements = [
        CandleRequirement(
            timeframe=timeframe,
            pairs=tuple(sorted(pair_bars)),
            bar_count=max(pair_bars.values()),
        )
        for timeframe, pair_bars in sorted(merged.items())
    ]
    return requirements, warnings
