"""AI Strategy lifecycle, spend gates, shadow execution, and guidance helpers."""

from __future__ import annotations

from brokerai.ai_strategy.lifecycle import (
    EXECUTION_PHASES,
    PHASE_LIVE,
    PHASE_READY,
    PHASE_WARMING,
    default_warmup_doc,
    ensure_lifecycle_on_create,
    get_execution_phase,
    is_ai_strategy_doc,
    is_catchup_context,
    normalize_lifecycle,
)

__all__ = [
    "EXECUTION_PHASES",
    "PHASE_LIVE",
    "PHASE_READY",
    "PHASE_WARMING",
    "default_warmup_doc",
    "ensure_lifecycle_on_create",
    "get_execution_phase",
    "is_ai_strategy_doc",
    "is_catchup_context",
    "normalize_lifecycle",
]
