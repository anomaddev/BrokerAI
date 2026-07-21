"""Tests for gated reverse-crossover exit protection."""

from __future__ import annotations

import pytest

from brokerai.backtesting.simulator import BacktestSimulator
from brokerai.strategies.params import ParamsValidationError
from brokerai.strategies.params.validate import validate_params
from brokerai.strategies.presets.ema_crossover.definition import DEFAULT_PARAMS
from brokerai.strategies.registry import get_preset
from brokerai.trading.exit_analysis import trade_requires_exit_monitor
from brokerai.trading.indicator_cache import IndicatorCacheView
from brokerai.trading.pipeline import ensure_trading_registries
from brokerai.trading.presets.ema_crossover.exits import (
    EmaCrossoverExitFactory,
    ReverseCrossoverExitMonitor,
)
from brokerai.trading.registries.exits import create_exit_monitor


def _candle(time: str, close: float = 1.10) -> dict:
    return {
        "time": time,
        "open": close,
        "high": close + 0.001,
        "low": close - 0.001,
        "close": close,
        "volume": 1,
    }


def _times(n: int) -> list[str]:
    """Synthetic OANDA-style open times (15m steps from a fixed start)."""
    from datetime import datetime, timedelta, timezone

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        (start + timedelta(minutes=15 * i)).strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        for i in range(n)
    ]


def _series(times: list[str], values: list[float]) -> list[dict]:
    return [{"time": t, "value": v} for t, v in zip(times, values, strict=True)]


def _params(**rc_overrides) -> dict:
    rc = {
        "enabled": True,
        "min_bars_after_entry": 6,
        "min_confirmation_bars": 2,
        "min_separation_atr": 0.2,
        **rc_overrides,
    }
    return {
        **DEFAULT_PARAMS,
        "exits": {
            **DEFAULT_PARAMS["exits"],
            "take_profit": {"enabled": True, "mode": "reverse_crossover"},
            "reverse_crossover": rc,
        },
    }


def _long_trade(entry_time: str) -> dict:
    return {
        "id": "t1",
        "strategy_id": "s1",
        "pair": "EUR/USD",
        "direction": "long",
        "entry_price": 1.10,
        "entry_candle_open": entry_time,
        "entry_time": entry_time,
    }


def _cache(times: list[str], fast_vals: list[float], slow_vals: list[float], atr: float = 0.01):
    return IndicatorCacheView(
        pair="EUR/USD",
        timeframe="M15",
        _values={
            "ema:9:close": _series(times, fast_vals),
            "ema:21:close": _series(times, slow_vals),
            "atr:14:close": _series(times, [atr] * len(times)),
        },
    )


@pytest.mark.asyncio
async def test_reverse_exit_blocked_inside_min_bars_after_entry():
    times = _times(10)
    # Entry at bar 7; reverse confirmed on last 2 bars → bars_held=2 < 6
    entry = times[7]
    # long: need fast < slow for last 2 bars, and bar before that fast >= slow
    fast = [1.20] * 7 + [1.20, 1.08, 1.07]
    slow = [1.10] * 10
    candles = [_candle(t) for t in times]
    trade = _long_trade(entry)
    monitor = ReverseCrossoverExitMonitor(trade, _params(min_bars_after_entry=6))
    intent = await monitor.evaluate(trade, candles, _params(), _cache(times, fast, slow))
    assert intent is None


@pytest.mark.asyncio
async def test_reverse_exit_fires_after_protection_and_confirmation():
    times = _times(12)
    entry = times[0]
    # bars_held = 11 >= 6; confirmation=2 with crossover into reverse at index 10
    fast = [1.20] * 10 + [1.08, 1.07]
    slow = [1.10] * 12
    candles = [_candle(t) for t in times]
    trade = _long_trade(entry)
    params = _params(min_bars_after_entry=6, min_confirmation_bars=2, min_separation_atr=0.2)
    monitor = ReverseCrossoverExitMonitor(trade, params)
    intent = await monitor.evaluate(trade, candles, params, _cache(times, fast, slow, atr=0.01))
    assert intent is not None
    assert intent.reason == "reverse_crossover"
    assert intent.metadata["confirmation_bars"] == 2
    assert intent.metadata["bars_held"] == 11


@pytest.mark.asyncio
async def test_reverse_exit_disabled():
    times = _times(12)
    entry = times[0]
    fast = [1.20] * 10 + [1.08, 1.07]
    slow = [1.10] * 12
    candles = [_candle(t) for t in times]
    trade = _long_trade(entry)
    params = _params(enabled=False)
    monitor = ReverseCrossoverExitMonitor(trade, params)
    intent = await monitor.evaluate(trade, candles, params, _cache(times, fast, slow))
    assert intent is None


@pytest.mark.asyncio
async def test_reverse_exit_requires_separation():
    times = _times(12)
    entry = times[0]
    # Gap is 0.001, ATR=0.01 → gap/ATR=0.1 < 0.2
    fast = [1.20] * 10 + [1.099, 1.099]
    slow = [1.10] * 12
    candles = [_candle(t) for t in times]
    trade = _long_trade(entry)
    params = _params(min_separation_atr=0.2)
    monitor = ReverseCrossoverExitMonitor(trade, params)
    intent = await monitor.evaluate(trade, candles, params, _cache(times, fast, slow, atr=0.01))
    assert intent is None


def test_factory_attaches_when_enabled_with_rr_mode():
    ensure_trading_registries()
    params = {
        **DEFAULT_PARAMS,
        "exits": {
            **DEFAULT_PARAMS["exits"],
            "take_profit": {"enabled": True, "mode": "rr_ratio", "risk_reward_ratio": 2.0},
            "reverse_crossover": {
                "enabled": True,
                "min_bars_after_entry": 6,
                "min_confirmation_bars": 2,
                "min_separation_atr": 0.2,
            },
        },
    }
    trade = _long_trade("1")
    factory = EmaCrossoverExitFactory()
    assert factory.supports(trade, params) is True
    monitor = factory.create(trade, params)
    assert isinstance(monitor, ReverseCrossoverExitMonitor)
    assert trade_requires_exit_monitor(params) is True


def test_factory_skips_when_disabled_and_price_tp():
    ensure_trading_registries()
    params = {
        **DEFAULT_PARAMS,
        "exits": {
            **DEFAULT_PARAMS["exits"],
            "take_profit": {"enabled": True, "mode": "rr_ratio", "risk_reward_ratio": 2.0},
            "reverse_crossover": {
                "enabled": False,
                "min_bars_after_entry": 6,
                "min_confirmation_bars": 2,
                "min_separation_atr": 0.2,
            },
        },
    }
    trade = _long_trade("1")
    factory = EmaCrossoverExitFactory()
    assert factory.supports(trade, params) is False
    assert create_exit_monitor(trade, params) is None
    assert trade_requires_exit_monitor(params) is False


@pytest.mark.asyncio
async def test_atr_stop_still_closes_without_reverse_signal():
    ensure_trading_registries()
    params = {
        **DEFAULT_PARAMS,
        "exits": {
            "stop_loss": {"enabled": True, "mode": "fixed_pips", "fixed_pips": 10},
            "take_profit": {"enabled": True, "mode": "reverse_crossover"},
            "reverse_crossover": {
                "enabled": True,
                "min_bars_after_entry": 30,
                "min_confirmation_bars": 2,
                "min_separation_atr": 0.2,
            },
        },
    }
    sim = BacktestSimulator(pair="EUR/USD", params=params)
    candles = [_candle("1", 1.1)]
    pos = sim.open_position(
        strategy_id="s1",
        direction="long",
        entry_price=1.1,
        entry_time="1",
        candles=candles,
    )
    assert pos is not None and pos.stop_loss is not None
    hit = {
        "time": "2",
        "open": 1.1,
        "high": 1.1,
        "low": pos.stop_loss - 0.0001,
        "close": pos.stop_loss,
        "volume": 1,
    }
    closed = sim.check_sl_tp(hit)
    assert closed is not None
    assert closed["exit_reason"] == "stop_loss"


def test_validate_params_includes_reverse_crossover_defaults():
    preset = get_preset("ema_crossover")
    assert preset is not None
    result = validate_params(preset, {**DEFAULT_PARAMS})
    rc = result["exits"]["reverse_crossover"]
    assert rc["enabled"] is True
    assert rc["min_bars_after_entry"] == 6
    assert rc["min_confirmation_bars"] == 2
    assert rc["min_separation_atr"] == pytest.approx(0.2)


def test_validate_params_rejects_reverse_crossover_bounds():
    preset = get_preset("ema_crossover")
    assert preset is not None
    with pytest.raises(ParamsValidationError):
        validate_params(
            preset,
            {
                **DEFAULT_PARAMS,
                "exits": {
                    **DEFAULT_PARAMS["exits"],
                    "reverse_crossover": {
                        "enabled": True,
                        "min_bars_after_entry": 99,
                        "min_confirmation_bars": 2,
                        "min_separation_atr": 0.2,
                    },
                },
            },
        )
