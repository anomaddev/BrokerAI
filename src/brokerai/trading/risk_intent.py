from __future__ import annotations

from typing import Any

from brokerai.trading.indicators.atr import compute_atr
from brokerai.trading.types import AnalysisResult, TradeIntent

PIP_SIZE = 0.0001


def pip_size_for_pair(pair: str) -> float:
    """Return pip size for *pair* (0.01 for JPY quote, 0.0001 otherwise)."""
    if "/" in pair:
        quote = pair.split("/")[-1].strip().upper()
    else:
        quote = pair.strip().upper()[-3:]
    return 0.01 if quote == "JPY" else PIP_SIZE


def is_jpy_quote_pair(pair: str) -> bool:
    """Return True when *pair* quotes in JPY (USD/JPY, EUR_JPY, …)."""
    return pip_size_for_pair(pair) == 0.01


def fixed_pips_for_stop(stop_loss: dict[str, Any], pair: str) -> float:
    """Return the fixed-pip SL count for *pair*.

    Uses ``fixed_pips_jpy`` for JPY quotes (default 50 when omitted) and
    ``fixed_pips`` otherwise (default 15).
    """
    if is_jpy_quote_pair(pair):
        raw = stop_loss.get("fixed_pips_jpy")
        if raw is None:
            return 50.0
        return float(raw)
    raw = stop_loss.get("fixed_pips")
    if raw is None:
        return 15.0
    return float(raw)


def _recent_swing_low(candles: list[dict[str, Any]], lookback: int) -> float:
    slice_candles = candles[-max(lookback, 2) :]
    return min(float(candle["low"]) for candle in slice_candles)


def compute_sl_tp_prices(
    params: dict[str, Any],
    candles: list[dict[str, Any]],
    entry: float,
    direction: str,
    *,
    pair: str = "",
) -> tuple[float | None, float | None, str]:
    exits = params.get("exits") or {}
    stop_loss = exits.get("stop_loss") or {}
    take_profit = exits.get("take_profit") or {}
    atr_val = compute_atr(candles, 14)
    pip_size = pip_size_for_pair(pair) if pair else PIP_SIZE

    sl_mode = str(stop_loss.get("mode", "atr_based"))
    if sl_mode == "fixed_pips":
        sl_distance = fixed_pips_for_stop(stop_loss, pair) * pip_size
    elif sl_mode == "structure":
        swing_low = _recent_swing_low(candles, int(stop_loss.get("structure_lookback", 10)))
        sl_distance = max(entry - swing_low, atr_val * 0.5)
    else:
        sl_distance = atr_val * float(stop_loss.get("atr_multiplier", 1.5))

    tp_mode = str(take_profit.get("mode", "rr_ratio"))
    if tp_mode == "fixed_pips":
        tp_distance = float(take_profit.get("fixed_pips", 30)) * pip_size
    elif tp_mode == "atr_based":
        tp_distance = atr_val * float(take_profit.get("atr_multiplier", 2.5))
    elif tp_mode in {"reverse_crossover", "trailing_stop"}:
        tp_distance = None
    else:
        tp_distance = sl_distance * float(take_profit.get("risk_reward_ratio", 2.0))

    if direction == "long":
        stop = entry - sl_distance
        take = entry + tp_distance if tp_distance is not None else None
    else:
        stop = entry + sl_distance
        take = entry - tp_distance if tp_distance is not None else None

    return stop, take, tp_mode


def build_trade_intent(
    result: AnalysisResult,
    params: dict[str, Any],
    candles: list[dict[str, Any]],
    *,
    asset_class: str = "forex",
) -> TradeIntent | None:
    if result.direction is None or not candles:
        return None

    entry = float(candles[-1]["close"])
    stop, take, exit_mode = compute_sl_tp_prices(
        params,
        candles,
        entry,
        result.direction,
        pair=result.pair,
    )
    risk = params.get("risk") or {}

    return TradeIntent(
        strategy_id=result.strategy_id,
        strategy_name=result.strategy_name,
        pair=result.pair,
        asset_class=asset_class,
        direction=result.direction,
        confidence=result.confidence,
        entry_price=entry,
        stop_loss=stop,
        take_profit=take,
        exit_mode=exit_mode,
        risk_pct=float(risk.get("risk_per_trade_pct", 1.0)),
        metadata={
            "analysis": result.metadata,
            "execution_reason": str(result.metadata.get("signal") or result.signal_type),
            "timeframe": result.timeframe,
            "entry_candle_open": candles[-1].get("time"),
            **({"analysis_run_id": result.run_id} if result.run_id else {}),
        },
    )
