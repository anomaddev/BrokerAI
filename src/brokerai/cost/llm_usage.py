from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LlmUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    raw_usage: dict[str, Any]


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def parse_llm_usage(usage: dict[str, Any] | None) -> LlmUsage | None:
    """Normalize provider usage blocks into a common token shape.

    Supports OpenAI-compatible chat completions (``prompt_tokens`` /
    ``completion_tokens``) and xAI Responses API (``input_tokens`` /
    ``output_tokens``).
    """
    if not usage or not isinstance(usage, dict):
        return None

    input_tokens = _coerce_int(
        usage.get("prompt_tokens")
        if usage.get("prompt_tokens") is not None
        else usage.get("input_tokens")
    )
    output_tokens = _coerce_int(
        usage.get("completion_tokens")
        if usage.get("completion_tokens") is not None
        else usage.get("output_tokens")
    )
    total_tokens = _coerce_int(usage.get("total_tokens"))

    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None

    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    if input_tokens is None and total_tokens is not None and output_tokens is not None:
        input_tokens = max(0, total_tokens - output_tokens)
    if output_tokens is None and total_tokens is not None and input_tokens is not None:
        output_tokens = max(0, total_tokens - input_tokens)

    return LlmUsage(
        input_tokens=input_tokens or 0,
        output_tokens=output_tokens or 0,
        total_tokens=total_tokens or (input_tokens or 0) + (output_tokens or 0),
        raw_usage=dict(usage),
    )
