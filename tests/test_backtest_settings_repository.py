from __future__ import annotations

import pytest

from brokerai.db.repositories.backtest_settings import (
    BacktestSettingsRepository,
    normalize_backtest_settings,
)

pytestmark = pytest.mark.usefixtures("sqlite_db")


def test_normalize_clamps_concurrent():
    assert normalize_backtest_settings({"max_concurrent": 99})["max_concurrent"] == 10
    assert normalize_backtest_settings({"max_concurrent": 0})["max_concurrent"] == 1


def test_normalize_ai_feedback_defaults():
    settings = normalize_backtest_settings({})
    assert settings["ai_feedback_enabled"] is False
    assert settings["ai_feedback_auto_on_complete"] is False
    assert settings["ai_feedback_model_id"] is None
    assert settings["ai_feedback_model_name"] is None
    assert settings["ai_feedback_reasoning_effort"] == "medium"
    assert settings["daily_ai_strategy_backtest_enabled"] is False
    assert settings["daily_ai_strategy_backtest_period"] == "6m"


def test_normalize_ai_feedback_invalid_effort_falls_back():
    settings = normalize_backtest_settings({"ai_feedback_reasoning_effort": "ultra"})
    assert settings["ai_feedback_reasoning_effort"] == "medium"


@pytest.mark.asyncio
async def test_get_and_update_settings():
    repo = BacktestSettingsRepository()
    initial = await repo.get()
    assert initial["max_concurrent"] == 2
    assert initial["auto_start"] is True
    assert initial["ai_feedback_enabled"] is False

    updated = await repo.update(
        max_concurrent=4,
        auto_start=False,
        ai_feedback_enabled=True,
        ai_feedback_auto_on_complete=True,
        ai_feedback_model_id="model-1",
        ai_feedback_model_name="gpt-4o",
        ai_feedback_reasoning_effort="high",
        daily_ai_strategy_backtest_enabled=True,
        daily_ai_strategy_backtest_period="1y",
    )
    assert updated["max_concurrent"] == 4
    assert updated["auto_start"] is False
    assert updated["ai_feedback_enabled"] is True
    assert updated["ai_feedback_auto_on_complete"] is True
    assert updated["ai_feedback_model_id"] == "model-1"
    assert updated["ai_feedback_model_name"] == "gpt-4o"
    assert updated["ai_feedback_reasoning_effort"] == "high"
    assert updated["daily_ai_strategy_backtest_enabled"] is True
    assert updated["daily_ai_strategy_backtest_period"] == "1y"

    again = await repo.get()
    assert again == updated

    cleared = await repo.update(clear_ai_feedback_model=True)
    assert cleared["ai_feedback_model_id"] is None
    assert cleared["ai_feedback_model_name"] is None
