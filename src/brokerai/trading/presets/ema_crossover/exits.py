from __future__ import annotations

from typing import Any

from brokerai.trading.indicators._candles import candle_close
from brokerai.trading.indicator_cache import IndicatorCacheView, indicator_cache_key
from brokerai.trading.indicators.atr import compute_atr
from brokerai.trading.indicators.ema import compute_ema
from brokerai.trading.presets.ema_crossover.signal import _detect_crossover
from brokerai.trading.registries.exits import ExitMonitor, ExitMonitorFactory, register_exit_factory
from brokerai.trading.types import ExitIntent


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
        _ = trade
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

        trade_direction = str(self._trade.get("direction", "long"))
        opposite = "short" if trade_direction == "long" else "long"
        direction, confidence, metadata = _detect_crossover(
            fast,
            slow,
            [],
            direction_filter=opposite,
            confirmation=str(signal.get("confirmation", "close")),
        )
        if direction != opposite or confidence <= 0:
            return None
        return ExitIntent(
            trade_id=str(self._trade.get("id", "")),
            strategy_id=str(self._trade.get("strategy_id", "")),
            pair=str(self._trade.get("pair", "")),
            reason="reverse_crossover",
            metadata=metadata,
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
        exits = params.get("exits") or {}
        tp_mode = str((exits.get("take_profit") or {}).get("mode", ""))
        return tp_mode in {"reverse_crossover", "trailing_stop"}

    def create(self, trade: dict[str, Any], params: dict[str, Any]) -> ExitMonitor:
        tp_mode = str((params.get("exits") or {}).get("take_profit", {}).get("mode", ""))
        if tp_mode == "reverse_crossover":
            return ReverseCrossoverExitMonitor(trade, params)
        return TrailingStopExitMonitor(trade, params)


def register_ema_crossover_exits() -> None:
    register_exit_factory(EmaCrossoverExitFactory())
