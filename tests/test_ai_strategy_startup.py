"""Tests for AI Strategy create-time startup sequence + settings."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from brokerai.ai_strategy.startup import (
    ORIGIN_AI_STRATEGY_STARTUP,
    advance_startup_job,
    enqueue_ai_strategy_startup,
    required_reports_for_strategy,
    seed_digest_from_research,
)
from brokerai.backtesting.ai_feedback import is_ai_strategy_daily_run
from brokerai.db.repositories.ai_strategy_settings import (
    AiStrategySettingsRepository,
    normalize_ai_strategy_settings,
)
from brokerai.db.repositories.ai_strategy_startup import (
    STARTUP_PHASE_LOOPING,
    STARTUP_PHASE_SEEDING_DIGEST,
    STARTUP_STATUS_COMPLETED,
    STARTUP_STATUS_FAILED,
    STARTUP_STATUS_QUEUED,
    AiStrategyStartupJobsRepository,
)
from brokerai.db.repositories.strategy_learning import StrategyMemoryDigestsRepository
from brokerai.strategies.params import prepare_params
from brokerai.strategies.registry import get_preset

pytestmark = pytest.mark.usefixtures("sqlite_db")


def _strategy_doc(
    strategy_id: str = "strat-startup",
    *,
    use_daily: bool = True,
    use_brief: bool = True,
    use_debrief: bool = False,
    model_id: str = "model-1",
) -> dict:
    preset = get_preset("ai_strategy")
    assert preset is not None
    params = prepare_params(
        preset,
        {
            "schema_version": 1,
            "timeframe": "M15",
            "ai": {
                "llm_mode": "off",
                "model_id": model_id,
                "model_name": "gpt-test",
                "use_daily_report": use_daily,
                "use_weekly_brief": use_brief,
                "use_weekly_debrief": use_debrief,
                "learn_enabled": True,
            },
        },
    )
    params["ai"]["model_id"] = model_id
    params["ai"]["model_name"] = "gpt-test"
    params["ai"]["use_daily_report"] = use_daily
    params["ai"]["use_weekly_brief"] = use_brief
    params["ai"]["use_weekly_debrief"] = use_debrief
    return {
        "id": strategy_id,
        "name": "AI Startup",
        "preset_id": "ai_strategy",
        "params": params,
        "enabled": False,
    }


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


def test_normalize_ai_strategy_settings_clamps():
    settings = normalize_ai_strategy_settings(
        {
            "startup_loop_count": 99,
            "startup_timeout_minutes": 1,
            "startup_backtest_period": "nope",
        }
    )
    assert settings["startup_loop_count"] == 10
    assert settings["startup_timeout_minutes"] == 15
    assert settings["startup_backtest_period"] == "6m"
    assert settings["startup_enabled"] is True


@pytest.mark.asyncio
async def test_ai_strategy_settings_get_and_update():
    repo = AiStrategySettingsRepository()
    initial = await repo.get()
    assert initial["startup_enabled"] is True
    assert initial["startup_loop_count"] == 3

    updated = await repo.update(
        startup_enabled=False,
        startup_loop_count=5,
        startup_backtest_period="1y",
        startup_timeout_minutes=90,
    )
    assert updated["startup_enabled"] is False
    assert updated["startup_loop_count"] == 5
    assert updated["startup_backtest_period"] == "1y"
    assert updated["startup_timeout_minutes"] == 90

    again = await repo.get()
    assert again["startup_loop_count"] == 5


def test_required_reports_from_strategy_flags():
    assert required_reports_for_strategy(
        _strategy_doc(use_daily=True, use_brief=False, use_debrief=True)
    ) == ["daily_report", "weekly_debrief"]


def test_startup_origin_is_memory_oriented():
    assert is_ai_strategy_daily_run({"origin": ORIGIN_AI_STRATEGY_STARTUP}) is True
    assert is_ai_strategy_daily_run({"origin": "ai_strategy_daily"}) is True
    assert is_ai_strategy_daily_run({"origin": "manual"}) is False


@pytest.mark.asyncio
async def test_enqueue_respects_startup_enabled():
    settings = AiStrategySettingsRepository()
    await settings.update(startup_enabled=False)

    with patch(
        "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
        new=AsyncMock(return_value=_strategy_doc()),
    ):
        job = await enqueue_ai_strategy_startup("strat-startup")
    assert job is None

    await settings.update(startup_enabled=True)
    with patch(
        "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
        new=AsyncMock(return_value=_strategy_doc()),
    ):
        job = await enqueue_ai_strategy_startup("strat-startup")
    assert job is not None
    assert job["status"] == STARTUP_STATUS_QUEUED
    assert job["loop_target"] == 3
    assert "daily_report" in job["required_reports"]

    # Idempotent — second enqueue returns existing open job.
    with patch(
        "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
        new=AsyncMock(return_value=_strategy_doc()),
    ):
        again = await enqueue_ai_strategy_startup("strat-startup")
    assert again is not None
    assert again["id"] == job["id"]


@pytest.mark.asyncio
async def test_seed_digest_from_research_creates_queueable_digest():
    strategy = _strategy_doc()
    with (
        patch(
            "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
            new=AsyncMock(return_value=strategy),
        ),
        patch(
            "brokerai.ai_strategy.startup.AiModelsRepository.find_enabled_by_id",
            new=AsyncMock(return_value=_enabled_model()),
        ),
        patch(
            "brokerai.ai_strategy.startup._load_research_context",
            new=AsyncMock(return_value="Bias: bullish London session."),
        ),
        patch(
            "brokerai.ai_strategy.startup.analyze_with_model",
            new=AsyncMock(
                return_value=(
                    '{"standing_rules":["Prefer London continuation"],'
                    '"anti_rules":["Avoid chasing late NY"],'
                    '"summary":"Seeded"}'
                )
            ),
        ),
    ):
        digest = await seed_digest_from_research("strat-startup")

    assert digest["version"] == 1
    assert digest["source"] == "ai_strategy_startup_seed"
    latest = await StrategyMemoryDigestsRepository().get_latest("strat-startup")
    assert latest is not None
    assert latest["summary"] == "Seeded"


@pytest.mark.asyncio
async def test_advance_startup_skips_reports_and_seeds_then_loops():
    settings = AiStrategySettingsRepository()
    await settings.update(startup_enabled=True, startup_loop_count=2)

    strategy = _strategy_doc(use_daily=False, use_brief=False, use_debrief=False)
    with patch(
        "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
        new=AsyncMock(return_value=strategy),
    ):
        job = await enqueue_ai_strategy_startup("strat-startup")
    assert job is not None

    # No required reports → ensuring_reports should immediately move to seeding.
    with patch(
        "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
        new=AsyncMock(return_value=strategy),
    ):
        job = await advance_startup_job(job["id"])
    assert job is not None
    assert job["phase"] == STARTUP_PHASE_SEEDING_DIGEST

    with (
        patch(
            "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
            new=AsyncMock(return_value=strategy),
        ),
        patch(
            "brokerai.ai_strategy.startup.AiModelsRepository.find_enabled_by_id",
            new=AsyncMock(return_value=_enabled_model()),
        ),
        patch(
            "brokerai.ai_strategy.startup._load_research_context",
            new=AsyncMock(return_value="(none)"),
        ),
        patch(
            "brokerai.ai_strategy.startup.analyze_with_model",
            new=AsyncMock(
                return_value=(
                    '{"standing_rules":["Rule A"],"anti_rules":["Rule B"],"summary":"ok"}'
                )
            ),
        ),
    ):
        job = await advance_startup_job(job["id"])
    assert job is not None
    assert job["phase"] == STARTUP_PHASE_LOOPING
    assert job["seed_digest_version"] == 1

    # Queue first loop backtest (mocked create + completed feedback path).
    fake_run = {
        "id": "run-1",
        "status": "queued",
        "strategy_id": "strat-startup",
        "origin": ORIGIN_AI_STRATEGY_STARTUP,
    }
    with (
        patch(
            "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
            new=AsyncMock(return_value=strategy),
        ),
        patch(
            "brokerai.ai_strategy.startup.BacktestRunsRepository.create_queued_runs",
            new=AsyncMock(return_value=[fake_run]),
        ),
        patch(
            "brokerai.ai_strategy.startup._start_backtest_if_needed",
            new=AsyncMock(),
        ),
    ):
        job = await advance_startup_job(job["id"])
    assert job is not None
    assert job["current_backtest_run_id"] == "run-1"
    assert job["loop_index"] == 0

    completed_run = {**fake_run, "status": "completed"}
    with (
        patch(
            "brokerai.ai_strategy.startup.BacktestRunsRepository.get_by_id",
            new=AsyncMock(return_value=completed_run),
        ),
        patch(
            "brokerai.backtesting.ai_feedback.run_backtest_ai_feedback",
            new=AsyncMock(return_value=completed_run),
        ),
    ):
        job = await advance_startup_job(job["id"])
    assert job is not None
    assert job["loop_index"] == 1
    assert job["current_backtest_run_id"] is None

    # Second loop queue + complete → job completed.
    fake_run_2 = {**fake_run, "id": "run-2"}
    with (
        patch(
            "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
            new=AsyncMock(return_value=strategy),
        ),
        patch(
            "brokerai.ai_strategy.startup.BacktestRunsRepository.create_queued_runs",
            new=AsyncMock(return_value=[fake_run_2]),
        ),
        patch(
            "brokerai.ai_strategy.startup._start_backtest_if_needed",
            new=AsyncMock(),
        ),
    ):
        job = await advance_startup_job(job["id"])
    assert job["current_backtest_run_id"] == "run-2"

    with (
        patch(
            "brokerai.ai_strategy.startup.BacktestRunsRepository.get_by_id",
            new=AsyncMock(return_value={**fake_run_2, "status": "completed"}),
        ),
        patch(
            "brokerai.backtesting.ai_feedback.run_backtest_ai_feedback",
            new=AsyncMock(return_value={**fake_run_2, "status": "completed"}),
        ),
    ):
        job = await advance_startup_job(job["id"])
    assert job is not None
    assert job["status"] == STARTUP_STATUS_COMPLETED
    assert job["loop_index"] == 2


@pytest.mark.asyncio
async def test_startup_job_repo_mark_failed():
    repo = AiStrategyStartupJobsRepository()
    job = await repo.enqueue("s1", {"loop_target": 1, "required_reports": []})
    failed = await repo.mark_failed(job["id"], error="boom")
    assert failed is not None
    assert failed["status"] == STARTUP_STATUS_FAILED
    assert failed["error"] == "boom"
