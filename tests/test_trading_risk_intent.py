from tests.fixtures.mock_candles import generate_mock_candles
import pytest
from brokerai.trading.risk_intent import (
    build_trade_intent,
    compute_sl_tp_prices,
    fixed_pips_for_stop,
    pip_size_for_pair,
)
from brokerai.trading.types import AnalysisResult


def test_compute_sl_tp_prices_long():
    candles = generate_mock_candles(60)
    entry = float(candles[-1]["close"])
    params = {
        "exits": {
            "stop_loss": {"mode": "atr_based", "atr_multiplier": 1.5},
            "take_profit": {"mode": "rr_ratio", "risk_reward_ratio": 2.0},
        }
    }
    stop, take, mode = compute_sl_tp_prices(params, candles, entry, "long")
    assert stop is not None and stop < entry
    assert take is not None and take > entry
    assert mode == "rr_ratio"


def test_pip_size_for_jpy_quote():
    assert pip_size_for_pair("USD/JPY") == 0.01
    assert pip_size_for_pair("EUR/USD") == 0.0001


def test_fixed_pips_for_stop_jpy_vs_standard():
    assert fixed_pips_for_stop({"fixed_pips": 15, "fixed_pips_jpy": 50}, "EUR/USD") == 15.0
    assert fixed_pips_for_stop({"fixed_pips": 15, "fixed_pips_jpy": 50}, "USD/JPY") == 50.0
    assert fixed_pips_for_stop({"fixed_pips": 15}, "USD/JPY") == 50.0


def test_compute_sl_tp_prices_standard_fixed_pips():
    candles = generate_mock_candles(60)
    entry = 1.1
    params = {
        "exits": {
            "stop_loss": {
                "mode": "fixed_pips",
                "fixed_pips": 15,
                "fixed_pips_jpy": 50,
            },
            "take_profit": {"mode": "fixed_pips", "fixed_pips": 30},
        }
    }
    stop, take, _ = compute_sl_tp_prices(params, candles, entry, "long", pair="EUR/USD")
    assert stop == pytest.approx(entry - 0.0015)
    assert take == pytest.approx(entry + 0.003)


def test_compute_sl_tp_prices_jpy_fixed_pips():
    candles = generate_mock_candles(60)
    entry = 112.0
    params = {
        "exits": {
            "stop_loss": {
                "mode": "fixed_pips",
                "fixed_pips": 15,
                "fixed_pips_jpy": 50,
            },
            "take_profit": {"mode": "fixed_pips", "fixed_pips": 30},
        }
    }
    stop, take, _ = compute_sl_tp_prices(params, candles, entry, "long", pair="AUD/JPY")
    assert stop == pytest.approx(entry - 0.50)
    assert take == pytest.approx(entry + 0.30)


def test_compute_sl_tp_prices_jpy_missing_fixed_pips_jpy_defaults_to_50():
    candles = generate_mock_candles(60)
    entry = 112.0
    params = {
        "exits": {
            "stop_loss": {"mode": "fixed_pips", "fixed_pips": 15},
            "take_profit": {"mode": "fixed_pips", "fixed_pips": 30},
        }
    }
    stop, _, _ = compute_sl_tp_prices(params, candles, entry, "long", pair="USD/JPY")
    assert stop == pytest.approx(entry - 0.50)


def test_build_trade_intent():
    candles = generate_mock_candles(60)
    result = AnalysisResult(
        strategy_id="s1",
        strategy_name="S1",
        pair="EUR/USD",
        timeframe="M15",
        confidence=0.8,
        direction="long",
        min_candles=50,
        signal_type="ema_crossover",
    )
    params = {
        "exits": {
            "stop_loss": {"mode": "atr_based", "atr_multiplier": 1.5},
            "take_profit": {"mode": "rr_ratio", "risk_reward_ratio": 2.0},
        },
        "risk": {"risk_per_trade_pct": 1.0},
    }
    intent = build_trade_intent(result, params, candles)
    assert intent is not None
    assert intent.direction == "long"
    assert intent.entry_price == float(candles[-1]["close"])
