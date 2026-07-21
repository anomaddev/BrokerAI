from __future__ import annotations

from typing import Any

from brokerai.db.market_data_timeseries import candle_open_time_to_datetime
from brokerai.trading.indicators._candles import candle_close
from brokerai.trading.indicator_cache import IndicatorCacheView, indicator_cache_key
from brokerai.trading.indicators.atr import compute_atr, compute_atr_series
from brokerai.trading.indicators.ema import compute_ema
from brokerai.trading.registries.exits import ExitMonitor, ExitMonitorFactory, register_exit_factory
from brokerai.trading.types import ExitIntent

DEFAULT_REVERSE_CROSSOVER_PARAMS: dict[str, Any] = {
    "enabled": True,
    "min_bars_after_entry": 6,
    "min_confirmation_bars": 2,
    "min_separation_atr": 0.2,
}


def _reverse_crossover_config(params: dict[str, Any]) -> dict[str, Any]:
    exits = params.get("exits") or {}
    raw = exits.get("reverse_crossover") or {}
    return {**DEFAULT_REVERSE_CROSSOVER_PARAMS, **raw}


def _is_ema_crossover_signal(params: dict[str, Any]) -> bool:
    return str((params.get("signal") or {}).get("type", "")) == "ema_crossover"


def _reverse_crossover_monitor_requested(params: dict[str, Any]) -> bool:
    """True when nested RC exits are on, or legacy take_profit.mode selects RC."""
    if not _is_ema_crossover_signal(params):
        return False
    tp_mode = str((params.get("exits") or {}).get("take_profit", {}).get("mode", ""))
    if tp_mode == "reverse_crossover":
        return True
    # Only treat nested enabled when the block is present or defaults apply for EMA.
    exits = params.get("exits") or {}
    if "reverse_crossover" in exits:
        return bool((exits.get("reverse_crossover") or {}).get("enabled", True))
    # EMA strategies without an explicit block default to enabled (preset behavior).
    return True


def _entry_anchor(trade: dict[str, Any]) -> Any:
    return (
        trade.get("entry_candle_open")
        or trade.get("entry_time")
        or trade.get("open_time")
        or trade.get("opened_at")
    )


def _bars_held_since_entry(trade: dict[str, Any], candles: list[dict[str, Any]]) -> int | None:
    """Return closed bars since the entry candle, or None if the anchor is missing.

    Entry bar itself is ``0``. One bar after entry is ``1``.
    """
    if not candles:
        return None
    anchor = _entry_anchor(trade)
    if anchor is None:
        return None
    anchor_dt = candle_open_time_to_datetime(anchor)
    if anchor_dt is None:
        return None

    entry_index: int | None = None
    for index, candle in enumerate(candles):
        candle_dt = candle_open_time_to_datetime(candle.get("time"))
        if candle_dt is None:
            continue
        if candle_dt == anchor_dt:
            entry_index = index
            break
        # Fallback: first candle at or after the entry instant.
        if candle_dt > anchor_dt and entry_index is None:
            entry_index = index
            break
    if entry_index is None:
        return None
    return max(0, len(candles) - 1 - entry_index)


def _ema_value_at(series: list[dict[str, Any]], index: int, slow_map: dict[str, float]) -> tuple[float, float] | None:
    if index < 0 or index >= len(series):
        return None
    time_key = str(series[index]["time"])
    slow_val = slow_map.get(time_key)
    if slow_val is None:
        return None
    return float(series[index]["value"]), float(slow_val)


def _is_reverse_side(fast_val: float, slow_val: float, trade_direction: str) -> bool:
    if trade_direction == "long":
        return fast_val < slow_val
    return fast_val > slow_val


def _confirmed_reverse_crossover(
    fast: list[dict[str, Any]],
    slow: list[dict[str, Any]],
    *,
    trade_direction: str,
    min_confirmation_bars: int,
) -> tuple[bool, dict[str, Any]]:
    """Require opposite EMA relationship for N bars with a crossover into that state."""
    if len(fast) < min_confirmation_bars + 1:
        return False, {"signal": "none", "reason": "insufficient_bars"}

    slow_map = {str(point["time"]): float(point["value"]) for point in slow}
    end_index = len(fast) - 1
    start_index = end_index - min_confirmation_bars + 1

    for index in range(start_index, end_index + 1):
        pair = _ema_value_at(fast, index, slow_map)
        if pair is None:
            return False, {"signal": "none", "reason": "missing_ema"}
        fast_val, slow_val = pair
        if not _is_reverse_side(fast_val, slow_val, trade_direction):
            return False, {"signal": "none", "reason": "not_confirmed"}

    # Crossover into reverse state at the start of the confirmation streak.
    prev = _ema_value_at(fast, start_index - 1, slow_map)
    if prev is None:
        return False, {"signal": "none", "reason": "missing_prior_ema"}
    prev_fast, prev_slow = prev
    if _is_reverse_side(prev_fast, prev_slow, trade_direction):
        return False, {"signal": "none", "reason": "no_crossover_into_reverse"}

    curr = _ema_value_at(fast, end_index, slow_map)
    assert curr is not None
    curr_fast, curr_slow = curr
    signal = "bearish_cross" if trade_direction == "long" else "bullish_cross"
    return True, {
        "signal": signal,
        "crossover_time": str(fast[start_index]["time"]),
        "confirmation_bars": min_confirmation_bars,
        "fast": curr_fast,
        "slow": curr_slow,
    }


class ReverseCrossoverExitMonitor:
    exit_mode = "reverse_crossover"

    def __init__(self, trade: dict[str, Any], params: dict[str, Any]) -> None:
        self._trade = trade
        self._params = params

    async def evaluate(
        self,
        trade: dict[str, Any],
        candles: list[dict[str, Any]],
        params: dict[str, Any],
        indicators: IndicatorCacheView,
    ) -> ExitIntent | None:
        trade_doc = trade or self._trade
        cfg = _reverse_crossover_config(params)
        # Nested enabled is the master switch; legacy mode-only attach still
        # evaluates but only emits when nested enabled (or defaults) allow it.
        if not bool(cfg.get("enabled", True)):
            # Legacy: take_profit.mode=reverse_crossover with nested enabled=false
            # must never close on reverse crossover.
            return None

        min_bars_after_entry = int(cfg.get("min_bars_after_entry", 6))
        min_confirmation_bars = int(cfg.get("min_confirmation_bars", 2))
        min_separation_atr = float(cfg.get("min_separation_atr", 0.2))

        if min_bars_after_entry > 0:
            bars_held = _bars_held_since_entry(trade_doc, candles)
            if bars_held is None or bars_held < min_bars_after_entry:
                return None
        else:
            bars_held = _bars_held_since_entry(trade_doc, candles)

        signal = params.get("signal") or {}
        indicators_spec = params.get("indicators") or {}
        fast_ref = str(signal.get("fast_ref", "fast"))
        slow_ref = str(signal.get("slow_ref", "slow"))
        fast_spec = indicators_spec.get(fast_ref) or {"type": "ema", "period": 9}
        slow_spec = indicators_spec.get(slow_ref) or {"type": "ema", "period": 21}
        fast = indicators.get_series(
            indicator_cache_key("ema", int(fast_spec.get("period", 9)))
        ) or compute_ema(candles, int(fast_spec.get("period", 9)))
        slow = indicators.get_series(
            indicator_cache_key("ema", int(slow_spec.get("period", 21)))
        ) or compute_ema(candles, int(slow_spec.get("period", 21)))

        trade_direction = str(trade_doc.get("direction", "long"))
        confirmed, metadata = _confirmed_reverse_crossover(
            fast,
            slow,
            trade_direction=trade_direction,
            min_confirmation_bars=min_confirmation_bars,
        )
        if not confirmed:
            return None

        atr_filter = next(
            (
                item
                for item in (params.get("filters") or [])
                if isinstance(item, dict) and item.get("type") == "atr"
            ),
            None,
        )
        atr_period = int(atr_filter.get("period", 14)) if atr_filter else 14
        atr_series = indicators.get_series(
            indicator_cache_key("atr", atr_period)
        ) or compute_atr_series(candles, atr_period)
        atr_map = {str(point["time"]): float(point["value"]) for point in atr_series}
        time_key = str(fast[-1]["time"]) if fast else ""
        atr_val = atr_map.get(time_key)
        if atr_val is None or atr_val <= 0:
            atr_val = compute_atr(candles, atr_period)

        ema_gap = abs(float(metadata["fast"]) - float(metadata["slow"]))
        if min_separation_atr > 0:
            if atr_val <= 0 or (ema_gap / atr_val) < min_separation_atr:
                return None

        confidence = 0.70
        exit_metadata = dict(metadata)
        exit_metadata.update(
            {
                "confidence": confidence,
                "bars_held": bars_held,
                "min_bars_after_entry": min_bars_after_entry,
                "min_confirmation_bars": min_confirmation_bars,
                "min_separation_atr": min_separation_atr,
                "ema_gap": ema_gap,
                "ema_gap_atr": (ema_gap / atr_val) if atr_val else None,
                "atr": atr_val,
            }
        )
        return ExitIntent(
            trade_id=str(trade_doc.get("id", "")),
            strategy_id=str(trade_doc.get("strategy_id", "")),
            pair=str(trade_doc.get("pair", "")),
            reason="reverse_crossover",
            metadata=exit_metadata,
        )


class TrailingStopExitMonitor:
    exit_mode = "trailing_stop"

    def __init__(self, trade: dict[str, Any], params: dict[str, Any]) -> None:
        self._trade = trade
        self._params = params

    async def evaluate(
        self,
        trade: dict[str, Any],
        candles: list[dict[str, Any]],
        params: dict[str, Any],
        indicators: IndicatorCacheView,
    ) -> ExitIntent | None:
        _ = trade
        if not candles:
            return None

        exits = params.get("exits") or {}
        take_profit = exits.get("take_profit") or {}
        trail_mode = str(take_profit.get("trail_mode", "atr"))
        entry = float(self._trade.get("entry_price", candle_close(candles[-1])))
        current = candle_close(candles[-1])
        direction = str(self._trade.get("direction", "long"))

        if trail_mode == "ema_slow":
            slow_ref = str((params.get("signal") or {}).get("slow_ref", "slow"))
            slow_spec = (params.get("indicators") or {}).get(slow_ref) or {"period": 21}
            slow = indicators.get_series(
                indicator_cache_key("ema", int(slow_spec.get("period", 21)))
            ) or compute_ema(candles, int(slow_spec.get("period", 21)))
            if not slow:
                return None
            trail_level = float(slow[-1]["value"])
            if direction == "long" and current < trail_level:
                return ExitIntent(
                    trade_id=str(self._trade.get("id", "")),
                    strategy_id=str(self._trade.get("strategy_id", "")),
                    pair=str(self._trade.get("pair", "")),
                    reason="trail_ema_slow",
                    metadata={"trail_level": trail_level, "current": current},
                )
            if direction == "short" and current > trail_level:
                return ExitIntent(
                    trade_id=str(self._trade.get("id", "")),
                    strategy_id=str(self._trade.get("strategy_id", "")),
                    pair=str(self._trade.get("pair", "")),
                    reason="trail_ema_slow",
                    metadata={"trail_level": trail_level, "current": current},
                )
            return None

        multiplier = float(take_profit.get("trail_atr_multiplier", 1.5))
        atr_val = compute_atr(candles, 14)
        stop_distance = atr_val * multiplier
        if direction == "long" and current <= entry - stop_distance:
            return ExitIntent(
                trade_id=str(self._trade.get("id", "")),
                strategy_id=str(self._trade.get("strategy_id", "")),
                pair=str(self._trade.get("pair", "")),
                reason="trail_atr",
                metadata={"atr": atr_val, "stop_distance": stop_distance},
            )
        if direction == "short" and current >= entry + stop_distance:
            return ExitIntent(
                trade_id=str(self._trade.get("id", "")),
                strategy_id=str(self._trade.get("strategy_id", "")),
                pair=str(self._trade.get("pair", "")),
                reason="trail_atr",
                metadata={"atr": atr_val, "stop_distance": stop_distance},
            )
        return None


class EmaCrossoverExitFactory:
    def supports(self, trade: dict[str, Any], params: dict[str, Any]) -> bool:
        _ = trade
        if not _is_ema_crossover_signal(params):
            return False
        exits = params.get("exits") or {}
        tp_mode = str((exits.get("take_profit") or {}).get("mode", ""))
        if tp_mode == "trailing_stop":
            return True
        return _reverse_crossover_monitor_requested(params)

    def create(self, trade: dict[str, Any], params: dict[str, Any]) -> ExitMonitor:
        tp_mode = str((params.get("exits") or {}).get("take_profit", {}).get("mode", ""))
        if tp_mode == "trailing_stop":
            return TrailingStopExitMonitor(trade, params)
        return ReverseCrossoverExitMonitor(trade, params)


def register_ema_crossover_exits() -> None:
    register_exit_factory(EmaCrossoverExitFactory())
