"""Tests for AI Strategy Slice 2 — ModelSignalRuntime."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from brokerai.cost.llm_guard import LlmBudgetExceeded
from brokerai.strategies.params import prepare_params
from brokerai.strategies.registry import get_preset
from brokerai.trading.indicator_cache import IndicatorCache
from brokerai.trading.pipeline import ensure_trading_registries
from brokerai.trading.presets.ai_strategy.runtime import (
    ModelSignalRuntime,
    clear_decision_cache,
)
from brokerai.trading.registries.signals import get_signal_evaluator
from tests.fixtures.mock_candles import generate_mock_candles


@pytest.fixture(autouse=True)
def _clear_ai_decision_cache():
    clear_decision_cache()
    yield
    clear_decision_cache()


def _ai_params(**ai_overrides) -> dict:
    preset = get_preset("ai_strategy")
    assert preset is not None
    ai = {
        "llm_mode": "interval",
        "model_id": "model-1",
        "min_llm_interval_minutes": 15,
        "max_context_bars": 32,
        "use_daily_report": True,
    }
    ai.update(ai_overrides)
    return prepare_params(preset, {"schema_version": 1, "timeframe": "M15", "ai": ai})


def _enabled_model(*, model_id: str = "model-1") -> dict:
    return {
        "id": model_id,
        "enabled": True,
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-test",
        "api_key": "sk-test",
        "title": "Test Model",
    }


@pytest.mark.asyncio
async def test_llm_mode_off_never_calls_model():
    ensure_trading_registries()
    evaluator = get_signal_evaluator("ai_strategy")
    assert isinstance(evaluator, ModelSignalRuntime)

    params = _ai_params(llm_mode="off", model_id="model-1")
    candles = generate_mock_candles(80)
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [params])

    with patch(
        "brokerai.trading.presets.ai_strategy.runtime.analyze_with_model",
        new_callable=AsyncMock,
    ) as mock_llm:
        result = await evaluator.evaluate_async(
            candles,
            params,
            cache,
            strategy_id="s-off",
            pair="EUR/USD",
        )
        mock_llm.assert_not_called()

    assert result.direction is None
    assert result.confidence == 0.0
    assert result.metadata.get("llm_called") is False
    assert result.metadata.get("reason") == "llm_mode_off"


@pytest.mark.asyncio
async def test_interval_mode_enter_long_maps_direction():
    ensure_trading_registries()
    evaluator = ModelSignalRuntime()
    params = _ai_params(llm_mode="interval", model_id="model-1")
    candles = generate_mock_candles(80)
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [params])

    decision_json = (
        '{"action":"enter","direction":"long","confidence":0.82,'
        '"thesis":"bullish structure","invalidation":"break of lows"}'
    )

    with (
        patch(
            "brokerai.trading.presets.ai_strategy.runtime.AiModelsRepository"
        ) as mock_repo_cls,
        patch(
            "brokerai.trading.presets.ai_strategy.runtime.StrategyGuidanceRepository"
        ) as mock_guidance_cls,
        patch(
            "brokerai.trading.presets.ai_strategy.runtime.analyze_with_model",
            new_callable=AsyncMock,
            return_value=decision_json,
        ) as mock_llm,
    ):
        mock_repo_cls.return_value.find_enabled_by_id = AsyncMock(
            return_value=_enabled_model()
        )
        mock_guidance_cls.return_value.get_for_symbol = AsyncMock(
            return_value={
                "symbol": "EUR/USD",
                "signal": "buy",
                "tone": "bullish",
                "approach": "pullback",
                "conviction": "medium",
            }
        )

        result = await evaluator.evaluate_async(
            candles,
            params,
            cache,
            strategy_id="s-long",
            pair="EUR/USD",
        )

        mock_llm.assert_awaited_once()
        call_kwargs = mock_llm.await_args.kwargs
        assert call_kwargs["cost_context"]["operation"] == "ai_strategy_decision"
        assert call_kwargs["cost_context"]["strategy_id"] == "s-long"
        assert call_kwargs["cost_context"]["billable"] is True
        assert call_kwargs["cost_context"]["asof_id"] == str(candles[-1]["time"])

        # Guidance must appear as bias context, not orders.
        messages = mock_llm.await_args.args[3]
        user_content = messages[1]["content"]
        assert "bias" in user_content.lower() or "Research bias" in user_content
        assert "NOT orders" in user_content or "not orders" in user_content.lower()

    assert result.direction == "long"
    assert result.confidence == pytest.approx(0.82)
    assert result.metadata.get("llm_called") is True
    assert result.metadata.get("action") == "enter"
    assert result.metadata.get("thesis") == "bullish structure"


@pytest.mark.asyncio
async def test_missing_model_id_no_trade():
    ensure_trading_registries()
    evaluator = ModelSignalRuntime()
    params = _ai_params(llm_mode="interval", model_id=None)
    candles = generate_mock_candles(80)
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [params])

    with patch(
        "brokerai.trading.presets.ai_strategy.runtime.analyze_with_model",
        new_callable=AsyncMock,
    ) as mock_llm:
        result = await evaluator.evaluate_async(
            candles,
            params,
            cache,
            strategy_id="s-nomodel",
            pair="EUR/USD",
        )
        mock_llm.assert_not_called()

    assert result.direction is None
    assert result.metadata.get("reason") == "missing_model_id"
    assert result.metadata.get("llm_called") is False


@pytest.mark.asyncio
async def test_budget_exceeded_no_trade():
    ensure_trading_registries()
    evaluator = ModelSignalRuntime()
    params = _ai_params(llm_mode="interval", model_id="model-1")
    candles = generate_mock_candles(80)
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [params])

    with (
        patch(
            "brokerai.trading.presets.ai_strategy.runtime.AiModelsRepository"
        ) as mock_repo_cls,
        patch(
            "brokerai.trading.presets.ai_strategy.runtime.StrategyGuidanceRepository"
        ) as mock_guidance_cls,
        patch(
            "brokerai.trading.presets.ai_strategy.runtime.analyze_with_model",
            new_callable=AsyncMock,
            side_effect=LlmBudgetExceeded("daily_cap"),
        ) as mock_llm,
    ):
        mock_repo_cls.return_value.find_enabled_by_id = AsyncMock(
            return_value=_enabled_model()
        )
        mock_guidance_cls.return_value.get_for_symbol = AsyncMock(return_value=None)

        result = await evaluator.evaluate_async(
            candles,
            params,
            cache,
            strategy_id="s-budget",
            pair="EUR/USD",
        )
        mock_llm.assert_awaited_once()

    assert result.direction is None
    assert result.confidence == 0.0
    assert result.metadata.get("reason") == "budget_exceeded"
    assert result.metadata.get("llm_called") is False


@pytest.mark.asyncio
async def test_catchup_skips_llm():
    evaluator = ModelSignalRuntime()
    params = _ai_params(llm_mode="interval", model_id="model-1")
    candles = generate_mock_candles(80)
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [params])

    with patch(
        "brokerai.trading.presets.ai_strategy.runtime.analyze_with_model",
        new_callable=AsyncMock,
    ) as mock_llm:
        result = await evaluator.evaluate_async(
            candles,
            params,
            cache,
            catchup=True,
            strategy_id="s-catchup",
            pair="EUR/USD",
        )
        mock_llm.assert_not_called()

    assert result.direction is None
    assert result.metadata.get("reason") == "catchup"


@pytest.mark.asyncio
async def test_sync_evaluate_never_calls_llm_even_when_mode_on():
    evaluator = ModelSignalRuntime()
    params = _ai_params(llm_mode="interval", model_id="model-1")
    candles = generate_mock_candles(80)
    cache = IndicatorCache().warm("EUR/USD", "M15", candles, [params])

    with patch(
        "brokerai.trading.presets.ai_strategy.runtime.analyze_with_model",
        new_callable=AsyncMock,
    ) as mock_llm:
        result = evaluator.evaluate(candles, params, cache)
        mock_llm.assert_not_called()

    assert result.direction is None
    assert result.metadata.get("llm_called") is False
