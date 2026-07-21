from __future__ import annotations

from brokerai.bots.data_manager.candle_requirements import (
    collect_candle_requirements,
    htf_required_bars,
    required_candle_bars,
    strategy_extra_timeframes,
    strategy_timeframe,
)
from brokerai.integrations.oanda import forex_pair_to_instrument, timeframe_to_granularity


def test_strategy_timeframe_from_top_level():
    assert strategy_timeframe({"timeframe": "M15", "params": {"timeframe": "H1"}}) == "M15"


def test_required_candle_bars_uses_indicator_periods():
    strategy = {
        "params": {
            "indicators": {
                "fast": {"period": 9},
                "slow": {"period": 21},
            },
            "filters": [{"id": "adx", "enabled": True, "period": 14}],
            "exits": {"stop_loss": {"structure_lookback": 10}},
        }
    }
    assert required_candle_bars(strategy) == 63


def test_required_candle_bars_uses_stored_min_candles():
    strategy = {
        "params": {
            "min_candles": 200,
            "indicators": {"slow": {"period": 21}},
            "filters": [],
            "exits": {},
        }
    }
    assert required_candle_bars(strategy) == 200


def test_required_candle_bars_normalizes_preset_params():
    strategy = {
        "preset_id": "ema_crossover",
        "params": {
            "schema_version": 1,
            "timeframe": "M15",
            "min_candles": 120,
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
                    "threshold": 25,
                    "compare": "gte",
                }
            ],
            "exits": {
                "stop_loss": {"mode": "atr_based", "atr_multiplier": 1.5},
                "take_profit": {"mode": "rr_ratio", "risk_reward_ratio": 2.0},
            },
            "risk": {"risk_per_trade_pct": 1.0, "max_trades_per_day": 3},
            "execution": {
                "sessions": ["London", "NY"],
                "min_confidence": 60,
                "override_all_strategies": False,
                "priority": 50,
            },
        },
    }
    assert required_candle_bars(strategy) == 120


def test_collect_candle_requirements_groups_by_timeframe():
    strategies = [
        (
            {
                "name": "Fast",
                "timeframe": "M15",
                "params": {"indicators": {"slow": {"period": 21}}},
            },
            ["EUR/USD"],
        ),
        (
            {
                "name": "Slow",
                "timeframe": "M15",
                "params": {"indicators": {"slow": {"period": 50}}},
            },
            ["EUR/USD", "GBP/USD"],
        ),
        (
            {
                "name": "Hourly",
                "timeframe": "H1",
                "params": {"indicators": {"slow": {"period": 21}}},
            },
            ["EUR/USD"],
        ),
    ]

    requirements, warnings = collect_candle_requirements(strategies)

    assert warnings == []
    assert len(requirements) == 2

    m15 = next(item for item in requirements if item.timeframe == "M15")
    assert m15.pairs == ("EUR/USD", "GBP/USD")
    assert m15.bar_count == 150

    h1 = next(item for item in requirements if item.timeframe == "H1")
    assert h1.pairs == ("EUR/USD",)
    assert h1.bar_count == 63


def test_oanda_timeframe_mapping():
    assert timeframe_to_granularity("M15") == "M15"
    assert timeframe_to_granularity("D1") == "D"
    assert timeframe_to_granularity("M3") is None


def test_forex_pair_to_oanda_instrument():
    assert forex_pair_to_instrument("EUR/USD") == "EUR_USD"


def test_strategy_extra_timeframes_includes_htf_bias_and_additional():
    params = {
        "additional_timeframes": ["H1"],
        "indicators": {
            "fast": {"type": "ema", "period": 9},
            "slow": {"type": "ema", "period": 21},
        },
        "signal": {"type": "ema_crossover", "fast_ref": "fast", "slow_ref": "slow"},
        "filters": [
            {"id": "htf_bias", "type": "htf_bias", "enabled": True, "timeframe": "H4"},
        ],
    }
    extras = strategy_extra_timeframes(params)
    assert extras == ["H1", "H4"]
    assert htf_required_bars(params) == 63


def test_collect_candle_requirements_includes_htf_bias_timeframe():
    strategies = [
        (
            {
                "name": "EMA+HTF",
                "timeframe": "M15",
                "params": {
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
                            "id": "htf_bias",
                            "type": "htf_bias",
                            "enabled": True,
                            "timeframe": "H4",
                        }
                    ],
                    "additional_timeframes": ["H4"],
                },
            },
            ["USD/JPY", "EUR/USD"],
        ),
    ]

    requirements, warnings = collect_candle_requirements(strategies)
    assert warnings == []
    by_tf = {item.timeframe: item for item in requirements}
    assert "M15" in by_tf
    assert "H4" in by_tf
    assert by_tf["H4"].pairs == ("EUR/USD", "USD/JPY")
    assert by_tf["H4"].bar_count == 63


def test_collect_candle_requirements_skips_disabled_htf_bias():
    strategies = [
        (
            {
                "name": "NoHTF",
                "timeframe": "M15",
                "params": {
                    "indicators": {"slow": {"period": 21}},
                    "filters": [
                        {
                            "id": "htf_bias",
                            "type": "htf_bias",
                            "enabled": False,
                            "timeframe": "H4",
                        }
                    ],
                },
            },
            ["EUR/USD"],
        ),
    ]
    requirements, warnings = collect_candle_requirements(strategies)
    assert warnings == []
    assert [item.timeframe for item in requirements] == ["M15"]
