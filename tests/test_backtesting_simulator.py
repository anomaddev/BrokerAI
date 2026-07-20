from __future__ import annotations

import pytest

from brokerai.backtesting.simulator import BacktestSimulator, pip_size
from brokerai.strategies.presets.ema_crossover.definition import DEFAULT_PARAMS
from brokerai.trading.pipeline import ensure_trading_registries


def test_pip_size_jpy_vs_standard():
    assert pip_size("USD/JPY") == 0.01
    assert pip_size("EUR/USD") == 0.0001


def test_simulator_fixed_pips_jpy_stop_distance():
    params = {
        **DEFAULT_PARAMS,
        "exits": {
            "stop_loss": {
                "enabled": True,
                "mode": "fixed_pips",
                "fixed_pips": 15,
                "fixed_pips_jpy": 50,
            },
            "take_profit": {"enabled": False, "mode": "fixed_pips", "fixed_pips": 30},
        },
    }
    jpy = BacktestSimulator(pair="USD/JPY", params=params)
    eur = BacktestSimulator(pair="EUR/USD", params=params)
    candles = [
        {"time": "1", "open": 150.0, "high": 150.1, "low": 149.9, "close": 150.0, "volume": 1},
    ]
    eur_candles = [
        {"time": "1", "open": 1.1, "high": 1.101, "low": 1.099, "close": 1.1, "volume": 1},
    ]
    jpy_pos = jpy.open_position(
        strategy_id="s1",
        direction="long",
        entry_price=150.0,
        entry_time="1",
        candles=candles,
    )
    eur_pos = eur.open_position(
        strategy_id="s1",
        direction="long",
        entry_price=1.1,
        entry_time="1",
        candles=eur_candles,
    )
    assert jpy_pos is not None and eur_pos is not None
    assert jpy_pos.stop_loss == pytest.approx(150.0 - 0.50)
    assert eur_pos.stop_loss == pytest.approx(1.1 - 0.0015)


def test_simulator_uses_custom_initial_equity_for_sizing():
    params = {
        **DEFAULT_PARAMS,
        "risk": {**(DEFAULT_PARAMS.get("risk") or {}), "risk_per_trade_pct": 1.0},
        "exits": {
            "stop_loss": {"enabled": True, "mode": "fixed_pips", "fixed_pips": 10},
            "take_profit": {"enabled": False, "mode": "fixed_pips", "fixed_pips": 20},
        },
    }
    small = BacktestSimulator(pair="EUR/USD", params=params, initial_equity=10_000)
    large = BacktestSimulator(pair="EUR/USD", params=params, initial_equity=100_000)
    assert small.equity == 10_000.0
    assert large.equity == 100_000.0

    candles = [
        {"time": "1", "open": 1.1, "high": 1.101, "low": 1.099, "close": 1.1, "volume": 1},
    ]
    small_pos = small.open_position(
        strategy_id="s1",
        direction="long",
        entry_price=1.1,
        entry_time="1",
        candles=candles,
    )
    large_pos = large.open_position(
        strategy_id="s1",
        direction="long",
        entry_price=1.1,
        entry_time="1",
        candles=candles,
    )
    assert small_pos is not None and large_pos is not None
    assert large_pos.units == pytest.approx(small_pos.units * 10, rel=1e-6)


@pytest.mark.asyncio
async def test_simulator_stop_loss_long():
    ensure_trading_registries()
    params = {
        **DEFAULT_PARAMS,
        "exits": {
            "stop_loss": {"enabled": True, "mode": "fixed_pips", "fixed_pips": 10},
            "take_profit": {"enabled": False, "mode": "fixed_pips", "fixed_pips": 20},
        },
    }
    sim = BacktestSimulator(pair="EUR/USD", params=params)
    candles = [
        {"time": "1", "open": 1.1, "high": 1.101, "low": 1.099, "close": 1.1, "volume": 1},
    ]
    pos = sim.open_position(
        strategy_id="s1",
        direction="long",
        entry_price=1.1,
        entry_time="1",
        candles=candles,
    )
    assert pos is not None
    assert pos.stop_loss is not None

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
    assert not sim.has_open_position()
