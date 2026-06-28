from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyPreset(ABC):
    """Base class for strategy preset definitions."""

    id: str
    name: str
    description: str
    asset_classes: list[str]
    route: str
    signal_type: str
    default_params: dict[str, Any] = field(default_factory=dict)
    param_schema: dict[str, Any] = field(default_factory=dict)
    locked: bool = True
