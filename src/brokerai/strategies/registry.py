from __future__ import annotations

from typing import Any

from brokerai.strategies.base import StrategyPreset
from brokerai.strategies.presets.ai_strategy.definition import AI_STRATEGY_PRESET
from brokerai.strategies.presets.custom.definition import CUSTOM_PRESET
from brokerai.strategies.presets.ema_crossover.definition import EMA_CROSSOVER_PRESET

PRESETS: dict[str, StrategyPreset] = {
    EMA_CROSSOVER_PRESET.id: EMA_CROSSOVER_PRESET,
    CUSTOM_PRESET.id: CUSTOM_PRESET,
    AI_STRATEGY_PRESET.id: AI_STRATEGY_PRESET,
}


def get_preset(preset_id: str) -> StrategyPreset | None:
    return PRESETS.get(preset_id)


def list_presets() -> list[StrategyPreset]:
    return list(PRESETS.values())


def serialize_preset(preset: StrategyPreset) -> dict[str, Any]:
    return {
        "id": preset.id,
        "name": preset.name,
        "description": preset.description,
        "asset_classes": list(preset.asset_classes),
        "route": preset.route,
        "signal_type": preset.signal_type,
        "locked": preset.locked,
        "default_params": preset.default_params,
        "param_schema": preset.param_schema,
    }
