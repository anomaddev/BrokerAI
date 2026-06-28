from __future__ import annotations

import pytest

from brokerai.strategies.candles import compute_required_candles, effective_min_candles
from brokerai.strategies.params import ParamsValidationError, prepare_params
from brokerai.strategies.params.validate import validate_params
from brokerai.strategies.presets.ema_crossover.definition import DEFAULT_PARAMS
from brokerai.strategies.registry import get_preset


def test_validate_params_rejects_invalid_timeframe():
    preset = get_preset("ema_crossover")
    assert preset is not None
    with pytest.raises(ParamsValidationError):
        validate_params(preset, {**DEFAULT_PARAMS, "timeframe": "not-a-timeframe"})


def test_validate_params_accepts_default_ema_crossover():
    preset = get_preset("ema_crossover")
    assert preset is not None
    result = validate_params(preset, DEFAULT_PARAMS)
    assert result["timeframe"] == "M15"
    assert result["min_candles"] == 63
    assert result["execution"]["priority"] == 50
    assert "trailing" not in result["exits"]


def test_validate_params_accepts_reverse_crossover_with_ema_signal():
    preset = get_preset("ema_crossover")
    assert preset is not None
    params = {
        **DEFAULT_PARAMS,
        "exits": {
            **DEFAULT_PARAMS["exits"],
            "take_profit": {"mode": "reverse_crossover"},
        },
    }
    result = validate_params(preset, params)
    assert result["exits"]["take_profit"]["mode"] == "reverse_crossover"


def test_validate_params_accepts_trailing_stop_take_profit():
    preset = get_preset("ema_crossover")
    assert preset is not None
    params = {
        **DEFAULT_PARAMS,
        "exits": {
            **DEFAULT_PARAMS["exits"],
            "take_profit": {
                "mode": "trailing_stop",
                "trail_mode": "ema_slow",
                "trail_ema_ref": "slow",
            },
        },
    }
    result = validate_params(preset, params)
    assert result["exits"]["take_profit"]["mode"] == "trailing_stop"
    assert result["exits"]["take_profit"]["trail_mode"] == "ema_slow"


def test_validate_params_migrates_legacy_trailing_block():
    preset = get_preset("ema_crossover")
    assert preset is not None
    params = {
        **DEFAULT_PARAMS,
        "exits": {
            **DEFAULT_PARAMS["exits"],
            "take_profit": {"mode": "rr_ratio", "risk_reward_ratio": 2.0},
            "trailing": {"enabled": True, "atr_multiplier": 1.2},
        },
    }
    result = validate_params(preset, params)
    assert result["exits"]["take_profit"]["mode"] == "trailing_stop"
    assert result["exits"]["take_profit"]["trail_mode"] == "atr"
    assert "trailing" not in result["exits"]


def test_validate_params_rejects_min_candles_below_computed():
    preset = get_preset("ema_crossover")
    assert preset is not None
    with pytest.raises(ParamsValidationError):
        validate_params(preset, {**DEFAULT_PARAMS, "min_candles": 10})


def test_validate_params_rejects_min_candles_above_maximum():
    preset = get_preset("ema_crossover")
    assert preset is not None
    with pytest.raises(ParamsValidationError):
        validate_params(preset, {**DEFAULT_PARAMS, "min_candles": 2001})


def test_custom_preset_rejects_empty_signal():
    preset = get_preset("custom")
    assert preset is not None
    with pytest.raises(ParamsValidationError):
        prepare_params(preset, {"timeframe": "M15"})


def test_custom_preset_accepts_monthly_high_signal():
    preset = get_preset("custom")
    assert preset is not None
    params = prepare_params(
        preset,
        {
            "timeframe": "M15",
            "indicators": {},
            "signal": {"type": "monthly_high"},
            "filters": [],
            "exits": DEFAULT_PARAMS["exits"],
            "risk": DEFAULT_PARAMS["risk"],
            "execution": DEFAULT_PARAMS["execution"],
        },
    )
    assert params["signal"]["type"] == "monthly_high"
    assert params["min_candles"] == 93


def test_custom_preset_accepts_ema_crossover_signal():
    preset = get_preset("custom")
    assert preset is not None
    params = prepare_params(
        preset,
        {
            "timeframe": "M15",
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
            "filters": [],
            "exits": DEFAULT_PARAMS["exits"],
            "risk": DEFAULT_PARAMS["risk"],
            "execution": DEFAULT_PARAMS["execution"],
        },
    )
    assert params["signal"]["type"] == "ema_crossover"
    assert params["min_candles"] == 63
