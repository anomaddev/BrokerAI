"""Create-time AI Strategy startup sequence.

Phases:
1. ``ensuring_reports`` — start/wait for global research reports the strategy uses
2. ``seeding_digest`` — LLM drafts an initial memory digest from research
3. ``looping`` — N compiled-playbook backtests with synchronous memory feedback
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from brokerai.ai_strategy.compile_playbook import compile_playbook_strategy_doc
from brokerai.ai_strategy.daily_backtest import ORIGIN_AI_STRATEGY_DAILY
from brokerai.ai_strategy.lifecycle import is_ai_strategy_doc
from brokerai.ai_strategy.learning import (
    MAX_ANTI_RULES,
    MAX_STANDING_RULES,
    MAX_SUMMARY_CHARS,
    parse_learning_response,
)
from brokerai.ai_strategy.memory_digest import digest_is_queueable, digest_version_key, normalize_memory_digest
from brokerai.bots.researcher.llm import analyze_with_model
from brokerai.bots.researcher.reports import daily_report_exists, load_daily_report_content
from brokerai.bots.researcher.weekly import (
    preview_weekly_brief_skip_reason,
    preview_weekly_debrief_skip_reason,
)
from brokerai.cost.llm_guard import LlmBudgetExceeded
from brokerai.db.repositories.ai_models import AiModelsRepository, bind_source_model
from brokerai.db.repositories.ai_strategy_settings import AiStrategySettingsRepository
from brokerai.db.repositories.ai_strategy_startup import (
    STARTUP_PHASE_ENSURING_REPORTS,
    STARTUP_PHASE_LOOPING,
    STARTUP_PHASE_SEEDING_DIGEST,
    STARTUP_STATUS_COMPLETED,
    STARTUP_STATUS_FAILED,
    STARTUP_STATUS_QUEUED,
    STARTUP_STATUS_RUNNING,
    AiStrategyStartupJobsRepository,
)
from brokerai.db.repositories.backtest_runs import (
    BACKTEST_RUN_STATUS_CANCELLED,
    BACKTEST_RUN_STATUS_COMPLETED,
    BACKTEST_RUN_STATUS_FAILED,
    BACKTEST_RUN_STATUS_QUEUED,
    BACKTEST_RUN_STATUS_RUNNING,
    BacktestRunsRepository,
)
from brokerai.db.repositories.research_settings import ResearchSettingsRepository
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.db.repositories.strategy_learning import StrategyMemoryDigestsRepository
from brokerai.tasks.research import (
    start_daily_report_task,
    start_weekly_brief_task,
    start_weekly_debrief_task,
)

logger = logging.getLogger(__name__)

ORIGIN_AI_STRATEGY_STARTUP = "ai_strategy_startup"

REPORT_DAILY = "daily_report"
REPORT_WEEKLY_BRIEF = "weekly_brief"
REPORT_WEEKLY_DEBRIEF = "weekly_debrief"

# Re-export so feedback memory fork can treat startup runs like daily ones.
MEMORY_ORIENTED_ORIGINS = frozenset({ORIGIN_AI_STRATEGY_DAILY, ORIGIN_AI_STRATEGY_STARTUP})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ai_section(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    raw = params.get("ai")
    return dict(raw) if isinstance(raw, dict) else {}


def required_reports_for_strategy(strategy: dict[str, Any]) -> list[str]:
    ai = _ai_section(strategy.get("params"))
    required: list[str] = []
    if bool(ai.get("use_daily_report", True)):
        required.append(REPORT_DAILY)
    if bool(ai.get("use_weekly_brief", True)):
        required.append(REPORT_WEEKLY_BRIEF)
    if bool(ai.get("use_weekly_debrief", True)):
        required.append(REPORT_WEEKLY_DEBRIEF)
    return required


def _is_already_done_skip(reason: str | None) -> bool:
    if not reason:
        return False
    lowered = reason.lower()
    return "already ran" in lowered or "already exists" in lowered


def _is_hard_fail_skip(reason: str | None) -> bool:
    if not reason:
        return False
    lowered = reason.lower()
    return (
        "model" in lowered
        and ("not found" in lowered or "disabled" in lowered or "required" in lowered)
    ) or "contributor" in lowered


async def enqueue_ai_strategy_startup(
    strategy_id: str,
    *,
    force: bool = False,
    strategies_repo: StrategiesRepository | None = None,
    settings_repo: AiStrategySettingsRepository | None = None,
    jobs_repo: AiStrategyStartupJobsRepository | None = None,
) -> dict[str, Any] | None:
    """Enqueue a startup job after AI Strategy create (idempotent unless force)."""
    sid = (strategy_id or "").strip()
    if not sid:
        return None
    strategies_repo = strategies_repo or StrategiesRepository()
    settings_repo = settings_repo or AiStrategySettingsRepository()
    jobs_repo = jobs_repo or AiStrategyStartupJobsRepository()

    settings = await settings_repo.get()
    if not settings.get("startup_enabled") and not force:
        return None

    strategy = await strategies_repo.get_by_id(sid)
    if strategy is None or not is_ai_strategy_doc(strategy):
        return None

    if await jobs_repo.has_open_job(sid) and not force:
        return await jobs_repo.get_latest_for_strategy(sid)

    required = required_reports_for_strategy(strategy)
    return await jobs_repo.enqueue(
        sid,
        {
            "loop_index": 0,
            "loop_target": int(settings.get("startup_loop_count") or 3),
            "backtest_period": str(settings.get("startup_backtest_period") or "6m"),
            "timeout_minutes": int(settings.get("startup_timeout_minutes") or 180),
            "required_reports": required,
            "report_task_ids": {},
            "skipped_reports": [],
        },
    )


async def _load_research_context(strategy: dict[str, Any]) -> str:
    """Load truncated report text for the seed prompt based on strategy toggles."""
    from brokerai.bots.researcher.reports import list_reports, read_report

    ai = _ai_section(strategy.get("params"))
    chunks: list[str] = []
    today = _now().date().isoformat()

    if bool(ai.get("use_daily_report", True)):
        content = await load_daily_report_content(today)
        if content:
            chunks.append(f"### Daily report ({today})\n{content[:6000]}")

    reports = await list_reports(limit=40)
    if bool(ai.get("use_weekly_brief", True)):
        for meta in reports:
            if str(getattr(meta, "report_type", "") or "") != "weekly_brief":
                continue
            try:
                _, text = await read_report(meta.filename)
                chunks.append(f"### Weekly brief ({meta.filename})\n{(text or '')[:6000]}")
            except Exception:
                logger.exception("Failed loading weekly brief for startup seed")
            break
    if bool(ai.get("use_weekly_debrief", True)):
        for meta in reports:
            if str(getattr(meta, "report_type", "") or "") != "weekly_debrief":
                continue
            try:
                _, text = await read_report(meta.filename)
                chunks.append(f"### Weekly debrief ({meta.filename})\n{(text or '')[:6000]}")
            except Exception:
                logger.exception("Failed loading weekly debrief for startup seed")
            break

    if not chunks:
        # Soft fallback: still allow seed from empty research with market-agnostic defaults.
        return "(No research report content available yet. Draft cautious, general forex standing/anti rules.)"
    return "\n\n".join(chunks)


async def seed_digest_from_research(
    strategy_id: str,
    *,
    strategies_repo: StrategiesRepository | None = None,
    digests_repo: StrategyMemoryDigestsRepository | None = None,
    models_repo: AiModelsRepository | None = None,
) -> dict[str, Any]:
    """Call the strategy model once to create an initial queueable memory digest."""
    strategies_repo = strategies_repo or StrategiesRepository()
    digests_repo = digests_repo or StrategyMemoryDigestsRepository()
    models_repo = models_repo or AiModelsRepository()

    strategy = await strategies_repo.get_by_id(strategy_id)
    if strategy is None:
        raise ValueError(f"strategy not found: {strategy_id}")
    ai = _ai_section(strategy.get("params"))
    model_id = ai.get("model_id")
    if not model_id:
        raise ValueError("params.ai.model_id missing for startup seed")

    source = await models_repo.find_enabled_by_id(str(model_id))
    if source is None:
        raise ValueError(f"model missing or disabled: {model_id}")
    bound = bind_source_model(
        source, str(ai.get("model_name")).strip() if ai.get("model_name") else None
    )
    model_type = str(bound.get("type") or "")
    base_url = str(bound.get("base_url") or "")
    model_name = str(bound.get("model_name") or "")
    api_key = bound.get("api_key") or None
    if not model_type or not base_url or not model_name:
        raise ValueError("model incomplete for startup seed")

    research = await _load_research_context(strategy)
    system = (
        "You are BrokerAI's AI Strategy bootstrap engine. "
        "Given research reports (daily/weekly), draft an initial memory digest for a new "
        "forex AI Strategy. Return ONLY a single JSON object (no markdown) with keys: "
        "standing_rules (string[]), anti_rules (string[]), summary (string). "
        "Standing rules: durable patterns that should bias entries. "
        "Anti-rules: patterns to avoid. Keep each rule short. Cap at 12 rules per list. "
        "Do not invent specific trade fills. Prefer cautious, evidence-grounded rules."
    )
    user = (
        f"Strategy id: {strategy_id}\n"
        f"Strategy name: {strategy.get('name') or 'AI Strategy'}\n"
        f"Timeframe: {(strategy.get('params') or {}).get('timeframe') or 'M15'}\n\n"
        f"Research context:\n{research}\n\n"
        "Respond with the Learning JSON only."
    )
    raw = await analyze_with_model(
        model_type,
        base_url,
        model_name,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        api_key if isinstance(api_key, str) else None,
        cost_context={
            "operation": "strategy_startup_seed",
            "source": "ai_strategy",
            "strategy_id": strategy_id,
            "billable": True,
        },
    )
    parsed = parse_learning_response(raw if isinstance(raw, str) else str(raw))
    if not parsed["standing_rules"] and not parsed["anti_rules"]:
        # Ensure queueable digest even if the model returns only a summary.
        parsed["standing_rules"] = [
            {
                "text": "Favor setups aligned with the latest research bias; stand aside when bias is flat.",
                "kind": "standing_rule",
            }
        ]
        parsed["anti_rules"] = [
            {
                "text": "Do not force entries against clear research anti-bias or thin-liquidity conditions.",
                "kind": "anti_rule",
            }
        ]
        if not parsed["summary"]:
            parsed["summary"] = "Bootstrap digest seeded from research with cautious defaults."

    version = await digests_repo.next_version(strategy_id)
    digest = await digests_repo.create_version(
        strategy_id,
        {
            "standing_rules": parsed["standing_rules"][:MAX_STANDING_RULES],
            "anti_rules": parsed["anti_rules"][:MAX_ANTI_RULES],
            "summary": (parsed["summary"] or "")[:MAX_SUMMARY_CHARS],
            "source": "ai_strategy_startup_seed",
            "model_id": str(model_id),
            "outcome_ids": [],
            "win_count": 0,
            "loss_count": 0,
            "covered_through": None,
            "prior_version": None,
        },
        version=version,
    )
    if not digest_is_queueable(digest):
        raise ValueError("seeded digest is not queueable")
    return digest


async def _ensure_reports_phase(job: dict[str, Any]) -> dict[str, Any]:
    """Advance ensuring_reports: start missing runnable reports; wait until ready."""
    jobs_repo = AiStrategyStartupJobsRepository()
    research = await ResearchSettingsRepository().get()
    now = _now()
    required = list(job.get("required_reports") or [])
    skipped = list(job.get("skipped_reports") or [])
    task_ids = dict(job.get("report_task_ids") or {})
    pending: list[str] = []

    # Daily first when both daily + brief are required.
    ordered = [r for r in (REPORT_DAILY, REPORT_WEEKLY_BRIEF, REPORT_WEEKLY_DEBRIEF) if r in required]

    for kind in ordered:
        if kind in skipped:
            continue
        if kind == REPORT_DAILY:
            today = now.date().isoformat()
            if research.get("last_daily_run_date") == today or await daily_report_exists(today):
                continue
            contributors = [
                c
                for c in (research.get("contributor_models") or [])
                if isinstance(c, dict) and c.get("enabled")
            ]
            if not contributors:
                return await jobs_repo.mark_failed(
                    str(job["id"]),
                    error="Daily report required but no enabled contributor models in Settings → Reports",
                ) or job
            if kind not in task_ids:
                task_id, err = await start_daily_report_task(force=False, manual=True)
                if err and "already" not in err.lower():
                    # Another task may be running — keep waiting.
                    logger.info("Startup daily report start note: %s", err)
                if task_id:
                    task_ids[kind] = task_id
            pending.append(kind)
            continue

        if kind == REPORT_WEEKLY_BRIEF:
            skip = await preview_weekly_brief_skip_reason(research, now, manual=True)
            if _is_already_done_skip(skip):
                continue
            if skip is None:
                if kind not in task_ids:
                    task_id, err = await start_weekly_brief_task(force=False, manual=True)
                    if err:
                        logger.info("Startup weekly brief start note: %s", err)
                    if task_id:
                        task_ids[kind] = task_id
                pending.append(kind)
                continue
            if _is_hard_fail_skip(skip):
                return await jobs_repo.mark_failed(str(job["id"]), error=skip) or job
            if "open-day daily" in (skip or "").lower():
                # Need open-day daily first — kick daily if not already pending.
                if REPORT_DAILY not in task_ids and REPORT_DAILY not in pending:
                    task_id, _err = await start_daily_report_task(force=False, manual=True)
                    if task_id:
                        task_ids[REPORT_DAILY] = task_id
                pending.append(kind)
                continue
            # Other soft skips: keep waiting.
            pending.append(kind)
            continue

        if kind == REPORT_WEEKLY_DEBRIEF:
            skip = await preview_weekly_debrief_skip_reason(research, now, manual=True)
            if _is_already_done_skip(skip):
                continue
            if skip is None:
                if kind not in task_ids:
                    task_id, err = await start_weekly_debrief_task(force=False, manual=True)
                    if err:
                        logger.info("Startup weekly debrief start note: %s", err)
                    if task_id:
                        task_ids[kind] = task_id
                pending.append(kind)
                continue
            if _is_hard_fail_skip(skip):
                return await jobs_repo.mark_failed(str(job["id"]), error=skip) or job
            # Not eligible yet (schedule / insufficient dailies) — skip without failing.
            if kind not in skipped:
                skipped.append(kind)
            continue

    await jobs_repo.patch_doc(
        str(job["id"]),
        {
            "report_task_ids": task_ids,
            "skipped_reports": skipped,
            "phase": STARTUP_PHASE_ENSURING_REPORTS,
            "pending_reports": pending,
        },
    )
    if pending:
        return await jobs_repo.get_by_id(str(job["id"])) or job

    # Reports ready → move to seed phase.
    return await jobs_repo.patch_doc(
        str(job["id"]),
        {
            "phase": STARTUP_PHASE_SEEDING_DIGEST,
            "pending_reports": [],
            "report_task_ids": task_ids,
            "skipped_reports": skipped,
        },
    ) or job


async def _seed_phase(job: dict[str, Any]) -> dict[str, Any]:
    jobs_repo = AiStrategyStartupJobsRepository()
    digests = StrategyMemoryDigestsRepository()
    existing = await digests.get_latest(str(job["strategy_id"]))
    if existing and digest_is_queueable(existing):
        return await jobs_repo.patch_doc(
            str(job["id"]),
            {
                "phase": STARTUP_PHASE_LOOPING,
                "seed_digest_version": existing.get("version"),
                "loop_index": int(job.get("loop_index") or 0),
            },
        ) or job

    try:
        digest = await seed_digest_from_research(str(job["strategy_id"]))
    except LlmBudgetExceeded as exc:
        return await jobs_repo.mark_failed(
            str(job["id"]), error=f"budget_exceeded: {exc.reason}"
        ) or job
    except Exception as exc:
        logger.exception("Startup seed failed strategy=%s", job.get("strategy_id"))
        return await jobs_repo.mark_failed(str(job["id"]), error=str(exc)) or job

    return await jobs_repo.patch_doc(
        str(job["id"]),
        {
            "phase": STARTUP_PHASE_LOOPING,
            "seed_digest_version": digest.get("version"),
            "loop_index": 0,
        },
    ) or job


async def _start_backtest_if_needed(run_id: str) -> None:
    """Ensure a queued startup backtest is claimed even when auto_start is off."""
    runs = BacktestRunsRepository()
    run = await runs.get_by_id(run_id)
    if run is None:
        return
    if run.get("status") != BACKTEST_RUN_STATUS_QUEUED:
        return
    updated = await runs.mark_running(run_id)
    if updated is None:
        return
    try:
        from brokerai.backtesting.coordinator import get_backtest_coordinator

        get_backtest_coordinator().notify_manual_start(run_id)
    except Exception:
        logger.exception("Failed to notify coordinator for startup run %s", run_id)


async def _loop_phase(job: dict[str, Any]) -> dict[str, Any]:
    jobs_repo = AiStrategyStartupJobsRepository()
    runs_repo = BacktestRunsRepository()
    digests_repo = StrategyMemoryDigestsRepository()
    strategies_repo = StrategiesRepository()

    loop_index = int(job.get("loop_index") or 0)
    loop_target = max(1, int(job.get("loop_target") or 3))
    period = str(job.get("backtest_period") or "6m")
    current_run_id = job.get("current_backtest_run_id")
    strategy_id = str(job["strategy_id"])

    if loop_index >= loop_target:
        return await jobs_repo.mark_completed(str(job["id"])) or job

    # Wait for in-flight backtest.
    if current_run_id:
        run = await runs_repo.get_by_id(str(current_run_id))
        if run is None:
            return await jobs_repo.mark_failed(
                str(job["id"]), error=f"startup backtest missing: {current_run_id}"
            ) or job
        status = str(run.get("status") or "")
        if status in {BACKTEST_RUN_STATUS_QUEUED, BACKTEST_RUN_STATUS_RUNNING}:
            await _start_backtest_if_needed(str(current_run_id))
            return job
        if status in {BACKTEST_RUN_STATUS_FAILED, BACKTEST_RUN_STATUS_CANCELLED}:
            return await jobs_repo.mark_failed(
                str(job["id"]), error=f"startup backtest {status}: {current_run_id}"
            ) or job
        if status == BACKTEST_RUN_STATUS_COMPLETED:
            # Synchronous memory feedback for this loop.
            try:
                from brokerai.backtesting.ai_feedback import run_backtest_ai_feedback

                await run_backtest_ai_feedback(str(current_run_id))
            except Exception as exc:
                logger.exception(
                    "Startup memory feedback failed run=%s strategy=%s",
                    current_run_id,
                    strategy_id,
                )
                # Soft-fail feedback: still count the loop so startup can finish.
                await jobs_repo.patch_doc(
                    str(job["id"]),
                    {"last_feedback_error": str(exc)[:1000]},
                )
            next_index = loop_index + 1
            patched = await jobs_repo.patch_doc(
                str(job["id"]),
                {
                    "loop_index": next_index,
                    "current_backtest_run_id": None,
                    "phase": STARTUP_PHASE_LOOPING,
                },
            )
            if next_index >= loop_target:
                return await jobs_repo.mark_completed(str(job["id"])) or patched or job
            return patched or job

    # Queue next loop.
    strategy = await strategies_repo.get_by_id(strategy_id)
    if strategy is None:
        return await jobs_repo.mark_failed(str(job["id"]), error="strategy not found") or job
    digest = await digests_repo.get_latest(strategy_id)
    compiled = compile_playbook_strategy_doc(strategy, digest)
    if compiled is None:
        return await jobs_repo.mark_failed(
            str(job["id"]), error="cannot compile playbook — digest missing/empty"
        ) or job

    digest_version = digest_version_key(normalize_memory_digest(digest))
    created = await runs_repo.create_queued_runs(
        [compiled],
        name=(
            f"{strategy.get('name') or 'AI Strategy'} startup loop "
            f"{loop_index + 1}/{loop_target}"
        ),
        period=period,
        origin=ORIGIN_AI_STRATEGY_STARTUP,
        cadence_key=f"startup:{strategy_id}:{job['id']}:{loop_index + 1}",
        digest_version=digest_version,
    )
    if not created:
        return await jobs_repo.mark_failed(str(job["id"]), error="failed to queue startup backtest") or job

    run_id = str(created[0].get("id") or "")
    await _start_backtest_if_needed(run_id)
    return await jobs_repo.patch_doc(
        str(job["id"]),
        {
            "current_backtest_run_id": run_id,
            "phase": STARTUP_PHASE_LOOPING,
            "loop_index": loop_index,
        },
    ) or job


async def advance_startup_job(job_id: str) -> dict[str, Any] | None:
    """Advance one startup job by a single drain step."""
    jobs_repo = AiStrategyStartupJobsRepository()
    job = await jobs_repo.get_by_id(job_id)
    if job is None:
        return None
    if job.get("status") in {STARTUP_STATUS_COMPLETED, STARTUP_STATUS_FAILED}:
        return job

    # Timeout guard.
    timeout_minutes = int(job.get("timeout_minutes") or 180)
    started_raw = job.get("started_at") or job.get("created_at")
    try:
        started = datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if _now() - started > timedelta(minutes=timeout_minutes):
            return await jobs_repo.mark_failed(
                job_id, error=f"startup timed out after {timeout_minutes} minutes"
            )

    except Exception:
        pass

    running = await jobs_repo.mark_running(job_id)
    job = running or job
    phase = str(job.get("phase") or STARTUP_PHASE_ENSURING_REPORTS)

    try:
        if phase == STARTUP_PHASE_ENSURING_REPORTS:
            return await _ensure_reports_phase(job)
        if phase == STARTUP_PHASE_SEEDING_DIGEST:
            return await _seed_phase(job)
        if phase == STARTUP_PHASE_LOOPING:
            return await _loop_phase(job)
        if phase == "done":
            return await jobs_repo.mark_completed(job_id)
        return await jobs_repo.mark_failed(job_id, error=f"unknown phase: {phase}")
    except Exception as exc:
        logger.exception("Startup advance failed job=%s", job_id)
        return await jobs_repo.mark_failed(job_id, error=str(exc))


async def drain_queued_startup_jobs(*, limit: int = 1) -> dict[str, Any]:
    """Secretary drain: advance up to ``limit`` open startup jobs."""
    jobs_repo = AiStrategyStartupJobsRepository()
    open_jobs = await jobs_repo.list_open(limit=max(1, min(int(limit), 10)))
    advanced = 0
    completed = 0
    failed = 0
    for job in open_jobs:
        result = await advance_startup_job(str(job["id"]))
        advanced += 1
        status = str((result or {}).get("status") or "")
        if status == STARTUP_STATUS_COMPLETED:
            completed += 1
        elif status == STARTUP_STATUS_FAILED:
            failed += 1
    return {
        "considered": len(open_jobs),
        "advanced": advanced,
        "completed": completed,
        "failed": failed,
    }
