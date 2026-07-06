from __future__ import annotations

from typing import Any

from brokerai.strategies.candles import effective_min_candles
from brokerai.strategies.evaluator import StrategyResult
from brokerai.trading.indicator_cache import IndicatorCacheView, indicator_cache_key
from brokerai.trading.indicators.adx import compute_adx
from brokerai.trading.indicators.atr import compute_atr_series
from brokerai.trading.indicators.ema import compute_ema
from brokerai.trading.registries.signals import register_signal

DEFAULT_APPROACHING_PARAMS: dict[str, Any] = {
    "enabled": True,
    "max_gap_atr": 0.5,
    "min_narrow_bars": 2,
}


def _series_at_time(series: list[dict[str, Any]], time_key: str) -> float | None:
    for point in series:
        if str(point.get("time")) == time_key:
            value = point.get("value")
            return float(value) if value is not None else None
    return None


def _detect_crossover(
    fast: list[dict[str, Any]],
    slow: list[dict[str, Any]],
    adx: list[dict[str, Any]],
    *,
    direction_filter: str,
    confirmation: str,
    catchup: bool = False,
    max_lookback: int = 5,
) -> tuple[str | None, float, dict[str, Any]]:
    """Detect an EMA crossover on the **current** (last) candle only.

    Live analysis runs when a new bar closes; a signal is emitted only when the
    crossover completes on that bar — the intended trade entry candle.

    When ``catchup`` is True (startup warm-up), scan backward up to
    ``max_lookback`` closed bars for the most recent crossover so a cross that
    occurred while the orchestrator was offline is not missed.
    """
    if len(fast) < 2:
        return None, 0.0, {"signal": "none"}

    slow_map = {str(point["time"]): float(point["value"]) for point in slow}
    adx_map = {str(point["time"]): float(point["value"]) for point in adx}

    start_index = len(fast) - 1
    end_index = max(1, len(fast) - max_lookback) if catchup else start_index

    for index in range(start_index, end_index - 1, -1):
        time_key = str(fast[index]["time"])
        prev_time = str(fast[index - 1]["time"])
        curr_fast = float(fast[index]["value"])
        prev_fast = float(fast[index - 1]["value"])
        slow_val = slow_map.get(time_key)
        prev_slow = slow_map.get(prev_time)
        if slow_val is None or prev_slow is None:
            continue

        bullish = prev_fast <= prev_slow and curr_fast > slow_val
        bearish = prev_fast >= prev_slow and curr_fast < slow_val
        if not bullish and not bearish:
            continue

        signal_direction = "long" if bullish else "short"
        if direction_filter == "long" and signal_direction != "long":
            continue
        if direction_filter == "short" and signal_direction != "short":
            continue

        if confirmation == "pullback" and index < 2:
            continue

        adx_val = adx_map.get(time_key, 20.0)
        confidence_pct = min(95.0, 50.0 + adx_val)
        metadata: dict[str, Any] = {
            "signal": "bullish_cross" if bullish else "bearish_cross",
            "crossover_time": time_key,
            "adx": adx_val,
            "confirmation": confirmation,
        }
        if catchup and index < start_index:
            metadata["catchup"] = True
        return signal_direction, confidence_pct / 100.0, metadata

    return None, 0.0, {"signal": "none"}


def _ema_gap_at_index(
    fast: list[dict[str, Any]],
    slow_map: dict[str, float],
    index: int,
) -> float | None:
    time_key = str(fast[index]["time"])
    slow_val = slow_map.get(time_key)
    if slow_val is None:
        return None
    return abs(float(fast[index]["value"]) - slow_val)


def _count_convergence_bars(
    fast: list[dict[str, Any]],
    slow_map: dict[str, float],
    end_index: int,
) -> int:
    """Count consecutive bars with shrinking EMA gap ending at ``end_index``."""
    count = 0
    for index in range(end_index, 0, -1):
        curr_gap = _ema_gap_at_index(fast, slow_map, index)
        prev_gap = _ema_gap_at_index(fast, slow_map, index - 1)
        if curr_gap is None or prev_gap is None:
            break
        if curr_gap >= prev_gap:
            break
        count += 1
    return count


def _approaching_confidence_pct(*, ema_gap: float, max_gap: float, adx_val: float) -> float:
    """Scale confidence below crossover levels; tighter gap yields higher score."""
    if max_gap <= 0:
        return 40.0
    proximity = max(0.0, min(1.0, 1.0 - (ema_gap / max_gap)))
    base = 40.0 + proximity * 25.0
    adx_boost = min(10.0, max(0.0, adx_val - 20.0) * 0.25)
    return min(75.0, base + adx_boost)


def _detect_approaching(
    fast: list[dict[str, Any]],
    slow: list[dict[str, Any]],
    adx: list[dict[str, Any]],
    atr: list[dict[str, Any]],
    *,
    direction_filter: str,
    confirmation: str,
    max_gap_atr: float = 0.5,
    min_narrow_bars: int = 2,
) -> tuple[str | None, float, dict[str, Any]]:
    """Detect EMA convergence on the **current** (last) candle only.

    Emits when fast and slow are close (within ``max_gap_atr * ATR``), the gap
    has narrowed for at least ``min_narrow_bars`` consecutive bars, and fast is
    moving toward an imminent crossover without having crossed yet.
    """
    min_bars = max(2, min_narrow_bars + 1)
    if len(fast) < min_bars:
        return None, 0.0, {"signal": "none"}

    slow_map = {str(point["time"]): float(point["value"]) for point in slow}
    adx_map = {str(point["time"]): float(point["value"]) for point in adx}
    atr_map = {str(point["time"]): float(point["value"]) for point in atr}

    index = len(fast) - 1
    time_key = str(fast[index]["time"])
    prev_time = str(fast[index - 1]["time"])
    curr_fast = float(fast[index]["value"])
    prev_fast = float(fast[index - 1]["value"])
    slow_val = slow_map.get(time_key)
    prev_slow = slow_map.get(prev_time)
    if slow_val is None or prev_slow is None:
        return None, 0.0, {"signal": "none"}

    atr_val = atr_map.get(time_key)
    if atr_val is None or atr_val <= 0:
        return None, 0.0, {"signal": "none"}

    ema_gap = abs(curr_fast - slow_val)
    max_gap = max_gap_atr * atr_val
    if ema_gap > max_gap:
        return None, 0.0, {"signal": "none"}

    convergence_bars = _count_convergence_bars(fast, slow_map, index)
    if convergence_bars < min_narrow_bars:
        return None, 0.0, {"signal": "none"}

    bullish = curr_fast < slow_val and curr_fast > prev_fast
    bearish = curr_fast > slow_val and curr_fast < prev_fast
    if not bullish and not bearish:
        return None, 0.0, {"signal": "none"}

    signal_direction = "long" if bullish else "short"
    if direction_filter == "long" and signal_direction != "long":
        return None, 0.0, {"signal": "none"}
    if direction_filter == "short" and signal_direction != "short":
        return None, 0.0, {"signal": "none"}

    if confirmation == "pullback" and index < 2:
        return None, 0.0, {"signal": "none"}

    adx_val = adx_map.get(time_key, 20.0)
    confidence_pct = _approaching_confidence_pct(
        ema_gap=ema_gap,
        max_gap=max_gap,
        adx_val=adx_val,
    )
    ema_gap_atr = ema_gap / atr_val
    metadata: dict[str, Any] = {
        "signal": "approaching_bullish_cross" if bullish else "approaching_bearish_cross",
        "signal_time": time_key,
        "adx": adx_val,
        "confirmation": confirmation,
        "ema_gap": ema_gap,
        "ema_gap_atr": ema_gap_atr,
        "atr": atr_val,
        "convergence_bars": convergence_bars,
        "fast_ema": curr_fast,
        "slow_ema": slow_val,
    }
    return signal_direction, confidence_pct / 100.0, metadata


class EmaCrossoverSignalEvaluator:
    signal_type = "ema_crossover"

    def evaluate(
        self,
        candles: list[dict[str, Any]],
        params: dict[str, Any],
        indicators: IndicatorCacheView,
        *,
        catchup: bool = False,
    ) -> StrategyResult:
        signal = params.get("signal") or {}
        indicators_spec = params.get("indicators") or {}
        fast_ref = str(signal.get("fast_ref", "fast"))
        slow_ref = str(signal.get("slow_ref", "slow"))
        fast_spec = indicators_spec.get(fast_ref) or {"type": "ema", "period": 9, "source": "close"}
        slow_spec = indicators_spec.get(slow_ref) or {"type": "ema", "period": 21, "source": "close"}

        fast_key = indicator_cache_key(
            str(fast_spec.get("type", "ema")),
            int(fast_spec.get("period", 9)),
            str(fast_spec.get("source", "close")),
        )
        slow_key = indicator_cache_key(
            str(slow_spec.get("type", "ema")),
            int(slow_spec.get("period", 21)),
            str(slow_spec.get("source", "close")),
        )

        fast = indicators.get_series(fast_key) or compute_ema(candles, int(fast_spec.get("period", 9)))
        slow = indicators.get_series(slow_key) or compute_ema(candles, int(slow_spec.get("period", 21)))

        adx_filter = next(
            (
                item
                for item in (params.get("filters") or [])
                if isinstance(item, dict) and item.get("type") == "adx" and item.get("enabled", True)
            ),
            None,
        )
        adx_period = int(adx_filter.get("period", 14)) if adx_filter else 14
        adx_key = indicator_cache_key("adx", adx_period)
        adx = indicators.get_series(adx_key) or compute_adx(candles, adx_period)

        atr_filter = next(
            (
                item
                for item in (params.get("filters") or [])
                if isinstance(item, dict) and item.get("type") == "atr" and item.get("enabled", True)
            ),
            None,
        )
        atr_period = int(atr_filter.get("period", 14)) if atr_filter else 14
        atr_key = indicator_cache_key("atr", atr_period)
        atr = indicators.get_series(atr_key) or compute_atr_series(candles, atr_period)

        direction_filter = str(signal.get("direction", "both"))
        confirmation = str(signal.get("confirmation", "close"))

        direction, confidence, metadata = _detect_crossover(
            fast,
            slow,
            adx,
            direction_filter=direction_filter,
            confirmation=confirmation,
            catchup=catchup,
        )

        approaching_cfg = {**DEFAULT_APPROACHING_PARAMS, **(signal.get("approaching") or {})}
        if (
            metadata.get("signal") == "none"
            and not catchup
            and approaching_cfg.get("enabled", True)
        ):
            direction, confidence, metadata = _detect_approaching(
                fast,
                slow,
                adx,
                atr,
                direction_filter=direction_filter,
                confirmation=confirmation,
                max_gap_atr=float(approaching_cfg.get("max_gap_atr", 0.5)),
                min_narrow_bars=int(approaching_cfg.get("min_narrow_bars", 2)),
            )

        return StrategyResult(
            confidence=confidence,
            min_candles=effective_min_candles(params),
            direction=direction,
            metadata=metadata,
        )


def register_ema_crossover_signal() -> None:
    register_signal("ema_crossover", EmaCrossoverSignalEvaluator())
