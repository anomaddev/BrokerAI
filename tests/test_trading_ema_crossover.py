from tests.fixtures.mock_candles import generate_mock_candles
from brokerai.trading.indicator_cache import IndicatorCache
from brokerai.trading.pipeline import run_strategy_analysis
from brokerai.trading.presets.ema_crossover import register_ema_crossover


def _ema_strategy_params() -> dict:
    return {
        "timeframe": "M15",
        "min_candles": 63,
        "indicators": {
            "fast": {"type": "ema", "period": 9, "source": "close"},
            "slow": {"type": "ema", "period": 21, "source": "close"},
        },
        "signal": {
            "type": "ema_crossover",
            "fast_ref": "fast",
            "slow_ref": "slow",
            "direction": "both",
            "confirmation": "close",
        },
        "filters": [
            {
                "id": "adx",
                "type": "adx",
                "enabled": True,
                "period": 14,
                "threshold": 15,
                "compare": "gte",
            },
            {
                "id": "atr",
                "type": "atr",
                "enabled": True,
                "period": 14,
                "min_value": 0.0008,
            },
        ],
        "exits": {
            "stop_loss": {"mode": "atr_based", "atr_multiplier": 1.5},
            "take_profit": {"mode": "rr_ratio", "risk_reward_ratio": 2.0},
        },
        "risk": {"risk_per_trade_pct": 1.0, "max_trades_per_day": 3},
        "execution": {
            "sessions": ["London"],
            "min_confidence": 0,
            "override_all_strategies": False,
            "priority": 50,
        },
    }


def test_run_strategy_analysis_returns_result():
    register_ema_crossover()
    candles = generate_mock_candles(120)
    strategy = {
        "id": "test-strategy",
        "name": "Test EMA",
        "timeframe": "M15",
        "preset_id": "ema_crossover",
        "params": _ema_strategy_params(),
    }
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [strategy["params"]])
    result = run_strategy_analysis(strategy, "EUR/USD", candles, cache, timeframe="M15")

    assert result.strategy_id == "test-strategy"
    assert result.pair == "EUR/USD"
    assert 0.0 <= result.confidence <= 1.0
    assert result.min_candles >= 21


def test_filter_chain_can_block_signal():
    register_ema_crossover()
    candles = generate_mock_candles(120)
    params = _ema_strategy_params()
    params["filters"][1]["min_value"] = 0.005
    strategy = {
        "id": "blocked",
        "name": "Blocked",
        "timeframe": "M15",
        "preset_id": "ema_crossover",
        "params": params,
    }
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [params])
    result = run_strategy_analysis(strategy, "EUR/USD", candles, cache, timeframe="M15")
    assert result.confidence == 0.0
    assert result.direction is None
