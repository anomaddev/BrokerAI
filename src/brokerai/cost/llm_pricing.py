from __future__ import annotations

from dataclasses import dataclass

from brokerai.cost.llm_usage import LlmUsage

# USD per 1M tokens. Update periodically from provider pricing pages.
# Keys: (provider_type, model_pattern) where pattern matches model_name prefix
# (trailing * is wildcard) or exact name.


@dataclass(frozen=True)
class ModelRates:
    input_per_million: float
    output_per_million: float


_RATES: dict[tuple[str, str], ModelRates] = {
    ("openai", "gpt-4o"): ModelRates(2.50, 10.00),
    ("openai", "gpt-4o-mini"): ModelRates(0.15, 0.60),
    ("openai", "gpt-4.1"): ModelRates(2.00, 8.00),
    ("openai", "gpt-4.1-mini"): ModelRates(0.40, 1.60),
    ("openai", "o3"): ModelRates(10.00, 40.00),
    ("openai", "o3-mini"): ModelRates(1.10, 4.40),
    # xAI catalog prices (USD / 1M tokens); longer prefixes win via startswith match.
    ("grok", "grok-4.5"): ModelRates(2.00, 6.00),
    ("grok", "grok-4.20"): ModelRates(1.25, 2.50),
    ("grok", "grok-4.3"): ModelRates(1.25, 2.50),
    ("grok", "grok-4"): ModelRates(3.00, 15.00),
    ("grok", "grok-3"): ModelRates(3.00, 15.00),
    ("grok", "grok-2"): ModelRates(2.00, 10.00),
    ("open_webui", "*"): ModelRates(0.0, 0.0),
}


def _match_rates(provider_type: str, model_name: str) -> ModelRates | None:
    normalized_model = (model_name or "").strip().lower()
    provider = (provider_type or "").strip().lower()

    exact = _RATES.get((provider, normalized_model))
    if exact is not None:
        return exact

    best: tuple[str, ModelRates] | None = None
    for (rate_provider, pattern), rates in _RATES.items():
        if rate_provider != provider:
            continue
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            if normalized_model.startswith(prefix):
                if best is None or len(prefix) > len(best[0]):
                    best = (prefix, rates)
        elif normalized_model.startswith(pattern):
            if best is None or len(pattern) > len(best[0]):
                best = (pattern, rates)
    return best[1] if best else None


def estimate_llm_cost_usd(
    provider_type: str | None,
    model_name: str,
    usage: LlmUsage,
) -> tuple[float | None, bool]:
    """Return ``(amount_usd, estimated)`` or ``(None, False)`` when unknown."""
    rates = _match_rates(provider_type or "", model_name)
    if rates is None:
        return None, False

    amount = (
        usage.input_tokens * rates.input_per_million
        + usage.output_tokens * rates.output_per_million
    ) / 1_000_000
    return round(amount, 8), True
