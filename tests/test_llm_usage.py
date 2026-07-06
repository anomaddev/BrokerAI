from __future__ import annotations

from brokerai.cost.llm_pricing import estimate_llm_cost_usd
from brokerai.cost.llm_usage import LlmUsage, parse_llm_usage


def test_parse_openai_compatible_usage():
    usage = parse_llm_usage(
        {"prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500}
    )
    assert usage is not None
    assert usage.input_tokens == 1200
    assert usage.output_tokens == 300
    assert usage.total_tokens == 1500


def test_parse_grok_responses_usage():
    usage = parse_llm_usage({"input_tokens": 800, "output_tokens": 150})
    assert usage is not None
    assert usage.input_tokens == 800
    assert usage.output_tokens == 150
    assert usage.total_tokens == 950


def test_parse_usage_returns_none_for_empty():
    assert parse_llm_usage(None) is None
    assert parse_llm_usage({}) is None


def test_estimate_gpt4o_cost():
    usage = LlmUsage(input_tokens=1_000_000, output_tokens=0, total_tokens=1_000_000, raw_usage={})
    amount, estimated = estimate_llm_cost_usd("openai", "gpt-4o", usage)
    assert estimated is True
    assert amount == 2.5


def test_estimate_unknown_model_returns_none():
    usage = LlmUsage(input_tokens=100, output_tokens=50, total_tokens=150, raw_usage={})
    amount, estimated = estimate_llm_cost_usd("openai", "unknown-model-xyz", usage)
    assert amount is None
    assert estimated is False
