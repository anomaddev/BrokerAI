from __future__ import annotations

import pytest

from brokerai.strategies.candles import compute_required_candles, effective_min_candles
from brokerai.strategies.params import ParamsValidationError, prepare_params
from brokerai.strategies.params.cleanup import prune_orphan_legacy_indicators
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
    assert result["execution"]["dont_hold_between_sessions"] is True
    assert result["execution"]["dont_hold_between_markets"] is True
    assert result["execution"]["close_before_market_hours"] == 2
    assert result["execution"]["no_late_market_trading"] is True
    assert result["execution"]["late_market_hours"] == 2
    assert "trailing" not in result["exits"]
    assert result["signal"]["approaching"]["enabled"] is True
    assert result["signal"]["approaching"]["max_gap_atr"] == 0.5
    assert result["exits"]["stop_loss"]["mode"] == "atr_based"
    assert result["exits"]["stop_loss"]["fixed_pips_jpy"] == 50


def test_validate_params_accepts_fixed_pips_jpy():
    preset = get_preset("ema_crossover")
    assert preset is not None
    result = validate_params(
        preset,
        {
            **DEFAULT_PARAMS,
            "exits": {
                **DEFAULT_PARAMS["exits"],
                "stop_loss": {
                    **DEFAULT_PARAMS["exits"]["stop_loss"],
                    "mode": "fixed_pips",
                    "fixed_pips": 20,
                    "fixed_pips_jpy": 80,
                },
            },
        },
    )
    assert result["exits"]["stop_loss"]["fixed_pips"] == 20
    assert result["exits"]["stop_loss"]["fixed_pips_jpy"] == 80


def test_validate_execution_market_hold_bounds():
    preset = get_preset("ema_crossover")
    assert preset is not None
    with pytest.raises(ParamsValidationError):
        validate_params(
            preset,
            {
                **DEFAULT_PARAMS,
                "execution": {
                    **DEFAULT_PARAMS["execution"],
                    "close_before_market_hours": 0,
                },
            },
        )
    with pytest.raises(ParamsValidationError):
        validate_params(
            preset,
            {
                **DEFAULT_PARAMS,
                "execution": {
                    **DEFAULT_PARAMS["execution"],
                    "late_market_hours": 25,
                },
            },
        )
    result = validate_params(
        preset,
        {
            **DEFAULT_PARAMS,
            "execution": {
                **DEFAULT_PARAMS["execution"],
                "dont_hold_between_sessions": True,
                "dont_hold_between_markets": True,
                "close_before_market_hours": 24,
                "no_late_market_trading": True,
                "late_market_hours": 1,
            },
        },
    )
    assert result["execution"]["dont_hold_between_sessions"] is True
    assert result["execution"]["close_before_market_hours"] == 24
    assert result["execution"]["late_market_hours"] == 1


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


def test_validate_params_rejects_legacy_trailing_block():
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
    with pytest.raises(ParamsValidationError):
        validate_params(preset, params)


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
            "exits": {
                "stop_loss": {
                    "enabled": True,
                    "mode": "fixed_pips",
                    "fixed_pips": 15,
                },
                "take_profit": {
                    "enabled": True,
                    "mode": "rr_ratio",
                    "risk_reward_ratio": 2.0,
                },
            },
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


def test_prepare_params_swaps_reversed_fast_slow_ema_refs():
    preset = get_preset("ema_crossover")
    assert preset is not None
    params = prepare_params(
        preset,
        {
            "schema_version": 1,
            "timeframe": "M15",
            "indicators": {
                "ema_a": {"type": "ema", "period": 21, "source": "close"},
                "ema_b": {"type": "ema", "period": 9, "source": "close"},
            },
            "signal": {
                "type": "ema_crossover",
                "fast_ref": "ema_a",
                "slow_ref": "ema_b",
                "direction": "both",
                "confirmation": "close",
            },
            "filters": DEFAULT_PARAMS["filters"],
            "exits": {
                **DEFAULT_PARAMS["exits"],
                "take_profit": {
                    "mode": "trailing_stop",
                    "trail_mode": "ema_slow",
                    "trail_ema_ref": "ema_b",
                },
            },
            "risk": DEFAULT_PARAMS["risk"],
            "execution": DEFAULT_PARAMS["execution"],
            "min_candles": 70,
        },
    )
    assert params["signal"]["fast_ref"] == "ema_b"
    assert params["signal"]["slow_ref"] == "ema_a"
    assert params["exits"]["take_profit"]["trail_ema_ref"] == "ema_a"


def test_prepare_params_replaces_indicators_when_payload_provides_them():
    """Component-id EMAs must not leave orphan fast/slow from preset defaults."""
    preset = get_preset("ema_crossover")
    assert preset is not None
    params = prepare_params(
        preset,
        {
            "schema_version": 1,
            "timeframe": "M15",
            "indicators": {
                "ema_fast1": {"type": "ema", "period": 9, "source": "close"},
                "ema_slow1": {"type": "ema", "period": 21, "source": "close"},
            },
            "signal": {
                "type": "ema_crossover",
                "fast_ref": "ema_fast1",
                "slow_ref": "ema_slow1",
                "direction": "both",
                "confirmation": "close",
            },
            "filters": DEFAULT_PARAMS["filters"],
            "exits": DEFAULT_PARAMS["exits"],
            "risk": DEFAULT_PARAMS["risk"],
            "execution": DEFAULT_PARAMS["execution"],
            "min_candles": 70,
        },
    )
    assert set(params["indicators"]) == {"ema_fast1", "ema_slow1"}
    assert "fast" not in params["indicators"]
    assert "slow" not in params["indicators"]
    assert params["signal"]["fast_ref"] == "ema_fast1"
    assert params["signal"]["slow_ref"] == "ema_slow1"


def test_prepare_params_keeps_default_indicators_when_omitted():
    preset = get_preset("ema_crossover")
    assert preset is not None
    params = prepare_params(preset, {"schema_version": 1, "timeframe": "H1"})
    assert "fast" in params["indicators"]
    assert "slow" in params["indicators"]
    assert params["signal"]["fast_ref"] == "fast"
    assert params["timeframe"] == "H1"


def test_prepare_params_persists_additional_timeframes_and_indicator_color():
    preset = get_preset("ema_crossover")
    assert preset is not None
    params = prepare_params(
        preset,
        {
            "schema_version": 1,
            "timeframe": "M15",
            "additional_timeframes": ["H1", "H4"],
            "indicators": {
                "ema_fast1": {
                    "type": "ema",
                    "period": 9,
                    "source": "close",
                    "color": "#3b82f6",
                },
                "ema_slow1": {
                    "type": "ema",
                    "period": 21,
                    "source": "close",
                    "color": "#f59e0b",
                },
            },
            "signal": {
                "type": "ema_crossover",
                "fast_ref": "ema_fast1",
                "slow_ref": "ema_slow1",
                "direction": "both",
                "confirmation": "close",
            },
            "filters": DEFAULT_PARAMS["filters"],
            "exits": DEFAULT_PARAMS["exits"],
            "risk": DEFAULT_PARAMS["risk"],
            "execution": DEFAULT_PARAMS["execution"],
            "min_candles": 70,
        },
    )
    assert params["additional_timeframes"] == ["H1", "H4"]
    assert params["indicators"]["ema_fast1"]["color"] == "#3b82f6"
    assert params["indicators"]["ema_slow1"]["color"] == "#f59e0b"


def test_validate_params_rejects_additional_timeframe_equal_to_primary():
    preset = get_preset("ema_crossover")
    assert preset is not None
    with pytest.raises(ParamsValidationError):
        validate_params(
            preset,
            {**DEFAULT_PARAMS, "additional_timeframes": ["M15"]},
        )


def test_prune_orphan_legacy_indicators_drops_unused_fast_slow():
    params = {
        "indicators": {
            "fast": {"type": "ema", "period": 9, "source": "close"},
            "slow": {"type": "ema", "period": 21, "source": "close"},
            "ema_a": {"type": "ema", "period": 9, "source": "close"},
            "ema_b": {"type": "ema", "period": 21, "source": "close"},
        },
        "signal": {
            "type": "ema_crossover",
            "fast_ref": "ema_a",
            "slow_ref": "ema_b",
        },
        "exits": {
            "take_profit": {
                "mode": "trailing_stop",
                "trail_mode": "ema_slow",
                "trail_ema_ref": "slow",
            }
        },
    }
    cleaned = prune_orphan_legacy_indicators(params)
    assert cleaned is not None
    assert set(cleaned["indicators"]) == {"ema_a", "ema_b"}
    assert cleaned["exits"]["take_profit"]["trail_ema_ref"] == "ema_b"


def test_prune_orphan_legacy_indicators_noop_for_legacy_only():
    assert prune_orphan_legacy_indicators(DEFAULT_PARAMS) is None
