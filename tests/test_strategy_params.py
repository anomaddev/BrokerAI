from __future__ import annotations

import pytest

from brokerai.strategies.params import ParamsValidationError
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
