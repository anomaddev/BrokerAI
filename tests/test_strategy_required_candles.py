from __future__ import annotations

from brokerai.strategies.candles import compute_required_candles, effective_min_candles


def test_compute_required_candles_uses_indicator_periods():
    params = {
        "indicators": {
            "fast": {"period": 9},
            "slow": {"period": 21},
        },
        "filters": [{"id": "adx", "enabled": True, "period": 14}],
        "exits": {"stop_loss": {"structure_lookback": 10}},
    }
    assert compute_required_candles(params) == 63


def test_effective_min_candles_uses_stored_floor_when_higher():
    params = {
        "min_candles": 200,
        "indicators": {"slow": {"period": 21}},
        "filters": [],
        "exits": {},
    }
    assert effective_min_candles(params) == 200


def test_effective_min_candles_uses_computed_when_stored_lower():
    params = {
        "min_candles": 50,
        "indicators": {"slow": {"period": 21}},
        "filters": [],
        "exits": {},
    }
    assert effective_min_candles(params) == 63
