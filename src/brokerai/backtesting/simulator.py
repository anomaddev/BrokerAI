"""In-memory fill / position / SL-TP simulator for backtests.

Fill model
----------
Entries fill at the **signal bar close** when confirmation mode is ``close``
(matching the EMA crossover live preset). Position size uses a fixed account
equity and ``risk.risk_per_trade_pct`` against the stop distance.

Exits
-----
1. Stop-loss / take-profit checked against bar high/low (intrabar).
2. Strategy exit monitors (reverse crossover, trailing stop) via the live
   ``create_exit_monitor`` factories — never places real broker orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from brokerai.trading.indicators.atr import compute_atr
from brokerai.trading.indicator_cache import IndicatorCacheView
from brokerai.trading.registries.exits import create_exit_monitor
from brokerai.trading.risk_intent import fixed_pips_for_stop, pip_size_for_pair
from brokerai.trading.types import ExitIntent

INITIAL_EQUITY = 10_000.0
DEFAULT_UNITS = 1000.0


def pip_size(pair: str) -> float:
    """Return one pip in price units for a forex pair (JPY quotes use 0.01)."""
    return pip_size_for_pair(pair)


@dataclass
class SimulatedPosition:
    id: str
    strategy_id: str
    pair: str
    direction: str
    entry_price: float
    units: float
    entry_time: str
    stop_loss: float | None = None
    take_profit: float | None = None
    status: str = "open"
    exit_price: float | None = None
    exit_time: str | None = None
    exit_reason: str | None = None
    realized_pnl: float = 0.0


@dataclass
class BacktestSimulator:
    pair: str
    params: dict[str, Any]
    initial_equity: float = INITIAL_EQUITY
    equity: float = field(init=False)
    position: SimulatedPosition | None = None
    closed_trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.initial_equity = max(0.0, float(self.initial_equity))
        self.equity = self.initial_equity

    def _risk_pct(self) -> float:
        risk = self.params.get("risk") or {}
        try:
            return max(0.01, float(risk.get("risk_per_trade_pct", 1.0)))
        except (TypeError, ValueError):
            return 1.0

    def _stop_take_levels(
        self,
        direction: str,
        entry: float,
        candles: list[dict[str, Any]],
    ) -> tuple[float | None, float | None]:
        exits = self.params.get("exits") or {}
        sl_cfg = exits.get("stop_loss") or {}
        tp_cfg = exits.get("take_profit") or {}
        pip = pip_size(self.pair)
        stop: float | None = None
        take: float | None = None

        if sl_cfg.get("enabled", True):
            mode = str(sl_cfg.get("mode", "fixed_pips"))
            if mode in {"atr", "atr_based"}:
                atr = compute_atr(candles, 14)
                dist = atr * float(sl_cfg.get("atr_multiplier", 1.5))
            else:
                dist = fixed_pips_for_stop(sl_cfg, self.pair) * pip
            if direction == "long":
                stop = entry - dist
            else:
                stop = entry + dist

        if tp_cfg.get("enabled", True):
            mode = str(tp_cfg.get("mode", "reverse_crossover"))
            if mode == "fixed_pips":
                dist = float(tp_cfg.get("fixed_pips", 30)) * pip
                take = entry + dist if direction == "long" else entry - dist
            elif mode == "risk_reward" and stop is not None:
                ratio = float(tp_cfg.get("risk_reward_ratio", 2.0))
                risk_dist = abs(entry - stop)
                take = (
                    entry + risk_dist * ratio
                    if direction == "long"
                    else entry - risk_dist * ratio
                )
            # reverse_crossover / trailing handled by exit monitors

        return stop, take

    def _position_units(self, entry: float, stop: float | None) -> float:
        if stop is None or entry == stop:
            return DEFAULT_UNITS
        risk_amount = self.equity * (self._risk_pct() / 100.0)
        stop_dist = abs(entry - stop)
        if stop_dist <= 0:
            return DEFAULT_UNITS
        units = risk_amount / stop_dist
        return max(1.0, round(units, 2))

    def _pnl(self, direction: str, entry: float, exit_price: float, units: float) -> float:
        if direction == "long":
            return (exit_price - entry) * units
        return (entry - exit_price) * units

    def _close(
        self,
        *,
        price: float,
        time: str,
        reason: str,
    ) -> dict[str, Any] | None:
        pos = self.position
        if pos is None or pos.status != "open":
            return None
        pnl = self._pnl(pos.direction, pos.entry_price, price, pos.units)
        pos.status = "closed"
        pos.exit_price = price
        pos.exit_time = time
        pos.exit_reason = reason
        pos.realized_pnl = pnl
        self.equity += pnl
        trade = {
            "id": pos.id,
            "strategy_id": pos.strategy_id,
            "pair": pos.pair,
            "direction": pos.direction,
            "entry_price": pos.entry_price,
            "exit_price": price,
            "entry_time": pos.entry_time,
            "exit_time": time,
            "units": pos.units,
            "status": "closed",
            "exit_reason": reason,
            "realized_pnl": pnl,
        }
        self.closed_trades.append(trade)
        self.position = None
        return trade

    def open_position(
        self,
        *,
        strategy_id: str,
        direction: str,
        entry_price: float,
        entry_time: str,
        candles: list[dict[str, Any]],
    ) -> SimulatedPosition | None:
        if self.position is not None:
            return None
        stop, take = self._stop_take_levels(direction, entry_price, candles)
        units = self._position_units(entry_price, stop)
        pos = SimulatedPosition(
            id=str(uuid4()),
            strategy_id=strategy_id,
            pair=self.pair,
            direction=direction,
            entry_price=entry_price,
            units=units,
            entry_time=entry_time,
            stop_loss=stop,
            take_profit=take,
        )
        self.position = pos
        return pos

    def check_sl_tp(self, candle: dict[str, Any]) -> dict[str, Any] | None:
        pos = self.position
        if pos is None:
            return None
        high = float(candle["high"])
        low = float(candle["low"])
        time = str(candle.get("time") or "")

        if pos.direction == "long":
            if pos.stop_loss is not None and low <= pos.stop_loss:
                return self._close(price=pos.stop_loss, time=time, reason="stop_loss")
            if pos.take_profit is not None and high >= pos.take_profit:
                return self._close(price=pos.take_profit, time=time, reason="take_profit")
        else:
            if pos.stop_loss is not None and high >= pos.stop_loss:
                return self._close(price=pos.stop_loss, time=time, reason="stop_loss")
            if pos.take_profit is not None and low <= pos.take_profit:
                return self._close(price=pos.take_profit, time=time, reason="take_profit")
        return None

    async def check_exit_monitors(
        self,
        candles: list[dict[str, Any]],
        indicators: IndicatorCacheView,
    ) -> dict[str, Any] | None:
        pos = self.position
        if pos is None or not candles:
            return None
        trade_doc = {
            "id": pos.id,
            "strategy_id": pos.strategy_id,
            "pair": pos.pair,
            "direction": pos.direction,
            "entry_price": pos.entry_price,
        }
        monitor = create_exit_monitor(trade_doc, self.params)
        if monitor is None:
            return None
        intent: ExitIntent | None = await monitor.evaluate(
            trade_doc, candles, self.params, indicators
        )
        if intent is None:
            return None
        price = float(candles[-1]["close"])
        return self._close(
            price=price,
            time=str(candles[-1].get("time") or ""),
            reason=intent.reason,
        )

    def mark_equity(self, candle: dict[str, Any]) -> None:
        pos = self.position
        equity = self.equity
        if pos is not None:
            mark = float(candle["close"])
            equity += self._pnl(pos.direction, pos.entry_price, mark, pos.units)
        self.equity_curve.append(
            {
                "time": str(candle.get("time") or ""),
                "equity": equity,
            }
        )

    def has_open_position(self) -> bool:
        return self.position is not None and self.position.status == "open"
