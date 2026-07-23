"""Tests for AI Strategy create-time startup sequence + settings."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from brokerai.ai_strategy.startup import (
    ORIGIN_AI_STRATEGY_STARTUP,
    advance_startup_job,
    cancel_ai_strategy_startup,
    enqueue_ai_strategy_startup,
    required_reports_for_strategy,
    seed_digest_from_research,
    startup_loop_mode,
)
from brokerai.backtesting.ai_feedback import is_ai_strategy_daily_run
from brokerai.db.repositories.ai_strategy_settings import (
    AiStrategySettingsRepository,
    normalize_ai_strategy_settings,
)
from brokerai.db.repositories.ai_strategy_startup import (
    STARTUP_PHASE_LOOPING,
    STARTUP_PHASE_SEEDING_DIGEST,
    STARTUP_STATUS_CANCELLED,
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


def test_startup_loop_mode_explore_then_trade():
    assert startup_loop_mode(0) == "explore"
    assert startup_loop_mode(1) == "trade"
    assert startup_loop_mode(2) == "trade"


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
        "loop_mode": "explore",
    }
    create_mock = AsyncMock(return_value=[fake_run])
    with (
        patch(
            "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
            new=AsyncMock(return_value=strategy),
        ),
        patch(
            "brokerai.ai_strategy.startup.BacktestRunsRepository.find_by_cadence_key",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "brokerai.ai_strategy.startup.BacktestRunsRepository.create_queued_runs",
            new=create_mock,
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
    assert create_mock.await_args.kwargs.get("loop_mode") == "explore"
    assert "Explore" in (job.get("status_message") or "")

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
    fake_run_2 = {**fake_run, "id": "run-2", "loop_mode": "trade"}
    create_mock_2 = AsyncMock(return_value=[fake_run_2])
    with (
        patch(
            "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
            new=AsyncMock(return_value=strategy),
        ),
        patch(
            "brokerai.ai_strategy.startup.BacktestRunsRepository.find_by_cadence_key",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "brokerai.ai_strategy.startup.BacktestRunsRepository.create_queued_runs",
            new=create_mock_2,
        ),
        patch(
            "brokerai.ai_strategy.startup._start_backtest_if_needed",
            new=AsyncMock(),
        ),
    ):
        job = await advance_startup_job(job["id"])
    assert job["current_backtest_run_id"] == "run-2"
    assert create_mock_2.await_args.kwargs.get("loop_mode") == "trade"
    assert "Trade" in (job.get("status_message") or "")

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


@pytest.mark.asyncio
async def test_attach_current_run_if_absent_is_idempotent():
    repo = AiStrategyStartupJobsRepository()
    job = await repo.enqueue(
        "s-attach",
        {"loop_target": 3, "required_reports": [], "loop_index": 0, "phase": "looping"},
    )
    await repo.mark_running(job["id"])
    first = await repo.attach_current_run_if_absent(
        job["id"], loop_index=0, run_id="run-a", status_message="queued a"
    )
    second = await repo.attach_current_run_if_absent(
        job["id"], loop_index=0, run_id="run-b", status_message="queued b"
    )
    assert first is not None and second is not None
    assert first["current_backtest_run_id"] == "run-a"
    assert second["current_backtest_run_id"] == "run-a"


@pytest.mark.asyncio
async def test_advance_loop_after_run_only_once():
    repo = AiStrategyStartupJobsRepository()
    job = await repo.enqueue(
        "s-advance",
        {
            "loop_target": 3,
            "required_reports": [],
            "loop_index": 0,
            "phase": "looping",
            "current_backtest_run_id": "run-1",
        },
    )
    await repo.mark_running(job["id"])
    # Ensure current run is attached for the open job.
    await repo.patch_doc(
        job["id"],
        {"loop_index": 0, "current_backtest_run_id": "run-1", "phase": "looping"},
    )
    first = await repo.advance_loop_after_run(
        job["id"],
        expected_run_id="run-1",
        expected_loop_index=0,
        next_loop_index=1,
        status_message="next",
    )
    second = await repo.advance_loop_after_run(
        job["id"],
        expected_run_id="run-1",
        expected_loop_index=0,
        next_loop_index=1,
        status_message="again",
    )
    assert first is not None and second is not None
    assert first["loop_index"] == 1
    assert first["current_backtest_run_id"] is None
    assert second["loop_index"] == 1
    assert second["current_backtest_run_id"] is None


@pytest.mark.asyncio
async def test_seed_waits_when_llm_budget_in_flight():
    from brokerai.cost.llm_guard import LlmBudgetExceeded

    settings = AiStrategySettingsRepository()
    await settings.update(startup_enabled=True, startup_loop_count=1)
    strategy = _strategy_doc(use_daily=False, use_brief=False, use_debrief=False)
    with patch(
        "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
        new=AsyncMock(return_value=strategy),
    ):
        job = await enqueue_ai_strategy_startup("strat-startup")
    job = await advance_startup_job(job["id"])
    assert job["phase"] == STARTUP_PHASE_SEEDING_DIGEST

    with (
        patch(
            "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
            new=AsyncMock(return_value=strategy),
        ),
        patch(
            "brokerai.ai_strategy.startup.seed_digest_from_research",
            new=AsyncMock(side_effect=LlmBudgetExceeded("in_flight")),
        ),
    ):
        job = await advance_startup_job(job["id"])
    assert job is not None
    assert job["status"] == "running"
    assert job["phase"] == STARTUP_PHASE_SEEDING_DIGEST
    assert "in_flight" in str(job.get("last_seed_wait") or "")


@pytest.mark.asyncio
async def test_ensure_reports_skips_brief_when_no_model_selected():
    """Missing weekly model must not leave startup queued forever."""
    settings = AiStrategySettingsRepository()
    await settings.update(startup_enabled=True, startup_loop_count=1)

    strategy = _strategy_doc(use_daily=True, use_brief=True, use_debrief=True)
    with patch(
        "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
        new=AsyncMock(return_value=strategy),
    ):
        job = await enqueue_ai_strategy_startup("strat-startup")
    assert job is not None
    assert "weekly_brief" in job["required_reports"]

    with (
        patch(
            "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
            new=AsyncMock(return_value=strategy),
        ),
        patch(
            "brokerai.ai_strategy.startup.ResearchSettingsRepository.get",
            new=AsyncMock(
                return_value={
                    "last_daily_run_date": "2026-07-22",
                    "contributor_models": [{"enabled": True}],
                }
            ),
        ),
        patch(
            "brokerai.ai_strategy.startup.daily_report_exists",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "brokerai.ai_strategy.startup.preview_weekly_brief_skip_reason",
            new=AsyncMock(return_value="No model selected for weekly_brief_model_id"),
        ),
        patch(
            "brokerai.ai_strategy.startup.preview_weekly_debrief_skip_reason",
            new=AsyncMock(return_value="No model selected for weekly_debrief_model_id"),
        ),
    ):
        job = await advance_startup_job(job["id"])

    assert job is not None
    assert job["status"] == "running"
    assert job["phase"] == STARTUP_PHASE_SEEDING_DIGEST
    assert "weekly_brief" in (job.get("skipped_reports") or [])
    assert "weekly_debrief" in (job.get("skipped_reports") or [])
    assert job.get("pending_reports") == []


@pytest.mark.asyncio
async def test_ensure_reports_starts_weeklies_with_relaxed_daily_prereqs():
    """Models selected + recent dailies → start weeklies even without open-day file."""
    settings = AiStrategySettingsRepository()
    await settings.update(startup_enabled=True, startup_loop_count=1)

    strategy = _strategy_doc(use_daily=True, use_brief=True, use_debrief=True)
    with patch(
        "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
        new=AsyncMock(return_value=strategy),
    ):
        job = await enqueue_ai_strategy_startup("strat-startup")
    assert job is not None

    brief_start = AsyncMock(return_value=("task-brief", None))
    debrief_start = AsyncMock(return_value=("task-debrief", None))
    with (
        patch(
            "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
            new=AsyncMock(return_value=strategy),
        ),
        patch(
            "brokerai.ai_strategy.startup.ResearchSettingsRepository.get",
            new=AsyncMock(
                return_value={
                    "last_daily_run_date": "2026-07-22",
                    "contributor_models": [{"enabled": True}],
                    "weekly_brief_model_id": "m1",
                    "weekly_debrief_model_id": "m1",
                }
            ),
        ),
        patch(
            "brokerai.ai_strategy.startup.daily_report_exists",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "brokerai.ai_strategy.startup.preview_weekly_brief_skip_reason",
            new=AsyncMock(return_value=None),
        ) as brief_preview,
        patch(
            "brokerai.ai_strategy.startup.preview_weekly_debrief_skip_reason",
            new=AsyncMock(return_value=None),
        ) as debrief_preview,
        patch(
            "brokerai.ai_strategy.startup.start_weekly_brief_task",
            new=brief_start,
        ),
        patch(
            "brokerai.ai_strategy.startup.start_weekly_debrief_task",
            new=debrief_start,
        ),
    ):
        job = await advance_startup_job(job["id"])

    assert job is not None
    assert "weekly_brief" in (job.get("pending_reports") or [])
    assert "weekly_debrief" in (job.get("pending_reports") or [])
    brief_preview.assert_awaited()
    assert brief_preview.await_args.kwargs.get("relax_daily_prereqs") is True
    debrief_preview.assert_awaited()
    assert debrief_preview.await_args.kwargs.get("relax_daily_prereqs") is True
    brief_start.assert_awaited()
    assert brief_start.await_args.kwargs.get("relax_daily_prereqs") is True
    debrief_start.assert_awaited()
    assert debrief_start.await_args.kwargs.get("relax_daily_prereqs") is True


@pytest.mark.asyncio
async def test_cancel_startup_marks_open_job_cancelled():
    settings = AiStrategySettingsRepository()
    await settings.update(startup_enabled=True, startup_loop_count=1)

    strategy = _strategy_doc()
    with patch(
        "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
        new=AsyncMock(return_value=strategy),
    ):
        job = await enqueue_ai_strategy_startup("strat-startup")
        assert job is not None
        assert job["status"] == STARTUP_STATUS_QUEUED

        cancelled = await cancel_ai_strategy_startup("strat-startup")

    assert cancelled is not None
    assert cancelled["id"] == job["id"]
    assert cancelled["status"] == STARTUP_STATUS_CANCELLED
    assert cancelled.get("error") == "Cancelled by user"
    assert await AiStrategyStartupJobsRepository().has_open_job("strat-startup") is False

    # Drain must not resurrect a cancelled job.
    advanced = await advance_startup_job(job["id"])
    assert advanced is not None
    assert advanced["status"] == STARTUP_STATUS_CANCELLED


@pytest.mark.asyncio
async def test_force_enqueue_cancels_open_job_then_restarts():
    settings = AiStrategySettingsRepository()
    await settings.update(startup_enabled=True, startup_loop_count=2)

    strategy = _strategy_doc()
    with patch(
        "brokerai.ai_strategy.startup.StrategiesRepository.get_by_id",
        new=AsyncMock(return_value=strategy),
    ):
        first = await enqueue_ai_strategy_startup("strat-startup")
        assert first is not None
        second = await enqueue_ai_strategy_startup("strat-startup", force=True)

    assert second is not None
    assert second["id"] != first["id"]
    assert second["status"] == STARTUP_STATUS_QUEUED

    first_after = await AiStrategyStartupJobsRepository().get_by_id(first["id"])
    assert first_after is not None
    assert first_after["status"] == STARTUP_STATUS_CANCELLED
    assert first_after.get("error") == "Superseded by restart"

    open_jobs = await AiStrategyStartupJobsRepository().list_open_for_strategy("strat-startup")
    assert len(open_jobs) == 1
    assert open_jobs[0]["id"] == second["id"]
