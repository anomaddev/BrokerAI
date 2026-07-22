"""Create-time AI Strategy startup sequence.

Phases:
1. ``ensuring_reports`` — start/wait for global research reports the strategy uses
2. ``seeding_digest`` — LLM drafts an initial memory digest from research
3. ``looping`` — N compiled-playbook backtests with synchronous memory feedback

Improve-loop semantics (anti-cheat, single shared sequence):
- ``loop_target`` is the total number of passes (default 3), not explore+trade
  counted separately.
- Loop 0 is **explore**: walk candles for patterns only (no fills).
- Loops 1..N-1 are **trade**: live-parity fills; learn from *this* run's outcomes.
- API and secretary both drain the job; cadence keys + atomic attach/advance keep
  each loop index to one backtest (no duplicate "loop" and "trade" pairs).
- Digests carry distilled lessons forward, but each loop must not reuse
  foreknowledge of the same period's path/returns from prior walks.
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
from brokerai.ai_strategy.startup_status import (
    build_startup_status_message,
    human_report_label,
)
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
    STARTUP_STATUS_CANCELLED,
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

LOOP_MODE_EXPLORE = "explore"
LOOP_MODE_TRADE = "trade"


def startup_loop_mode(loop_index: int) -> str:
    """First startup loop explores patterns; later loops trade live-parity.

    ``loop_index`` is 0-based. Index 0 → explore (signal-only). Index ≥ 1 → trade.
    """
    return LOOP_MODE_EXPLORE if int(loop_index) <= 0 else LOOP_MODE_TRADE


def _loop_progress_label(loop_index: int, loop_target: int) -> str:
    """Operator-facing label for the current improve loop."""
    target = max(1, int(loop_target))
    n = min(max(1, int(loop_index) + 1), target)
    mode = startup_loop_mode(loop_index)
    if mode == LOOP_MODE_EXPLORE:
        return f"Explore loop {n}/{target}"
    return f"Trade loop {n}/{target}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _progress_fields(job: dict[str, Any], *, status_message: str | None = None) -> dict[str, Any]:
    """Attach updated_at + status_message so the Log UI can show live progress."""
    merged = dict(job)
    if status_message is not None:
        merged["status_message"] = status_message
    return {
        "updated_at": _now().isoformat(),
        "status_message": status_message
        if status_message is not None
        else build_startup_status_message(merged),
    }


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
        "no model selected" in lowered
        or (
            "model" in lowered
            and (
                "not found" in lowered
                or "disabled" in lowered
                or "required" in lowered
                or "selected" in lowered
            )
        )
        or "contributor" in lowered
    )


def _is_permanent_report_skip(reason: str | None) -> bool:
    """True when waiting will never unblock (skip the report for startup)."""
    if not reason:
        return False
    if _is_hard_fail_skip(reason):
        return True
    lowered = reason.lower()
    return (
        "is disabled" in lowered
        or "schedule has not passed" in lowered
        or "no daily reports available" in lowered
    )


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

    if await jobs_repo.has_open_job(sid):
        if not force:
            return await jobs_repo.get_latest_for_strategy(sid)
        # Restart must close opens first so drain cannot race a second open job.
        await cancel_open_startup_jobs(
            sid,
            reason="Superseded by restart",
            jobs_repo=jobs_repo,
        )

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


async def cancel_open_startup_jobs(
    strategy_id: str,
    *,
    reason: str = "Cancelled by user",
    jobs_repo: AiStrategyStartupJobsRepository | None = None,
    backtests_repo: BacktestRunsRepository | None = None,
) -> list[dict[str, Any]]:
    """Cancel every open startup job for a strategy (and its in-flight backtest).

    Best-effort cancels report background tasks referenced by the job. Shared
    research reports are not deleted. Does not disable the strategy or reset
    warm-up / memory digests.
    """
    sid = (strategy_id or "").strip()
    if not sid:
        return []
    jobs_repo = jobs_repo or AiStrategyStartupJobsRepository()
    backtests_repo = backtests_repo or BacktestRunsRepository()
    open_jobs = await jobs_repo.list_open_for_strategy(sid, limit=50)
    cancelled: list[dict[str, Any]] = []
    for job in open_jobs:
        run_id = str(job.get("current_backtest_run_id") or "").strip()
        if run_id:
            try:
                await backtests_repo.request_cancel(run_id)
            except Exception:
                logger.exception(
                    "Startup cancel: failed to cancel backtest %s for job %s",
                    run_id,
                    job.get("id"),
                )
        task_ids = job.get("report_task_ids") or {}
        if isinstance(task_ids, dict):
            from brokerai.tasks.runner import cancel_task

            for task_id in task_ids.values():
                tid = str(task_id or "").strip()
                if not tid:
                    continue
                try:
                    await cancel_task(tid)
                except Exception:
                    logger.info(
                        "Startup cancel: report task %s not cancelled (may already be idle)",
                        tid,
                    )
        updated = await jobs_repo.mark_cancelled(str(job["id"]), reason=reason)
        if updated:
            cancelled.append(updated)
    return cancelled


async def cancel_ai_strategy_startup(
    strategy_id: str,
    *,
    reason: str = "Cancelled by user",
    strategies_repo: StrategiesRepository | None = None,
    jobs_repo: AiStrategyStartupJobsRepository | None = None,
) -> dict[str, Any] | None:
    """Cancel open startup for an AI Strategy. Returns the latest job snapshot.

    Returns ``None`` when the strategy id does not exist.
    Raises ``ValueError`` when the strategy is not an AI Strategy.
    """
    sid = (strategy_id or "").strip()
    if not sid:
        return None
    strategies_repo = strategies_repo or StrategiesRepository()
    jobs_repo = jobs_repo or AiStrategyStartupJobsRepository()
    strategy = await strategies_repo.get_by_id(sid)
    if strategy is None:
        return None
    if not is_ai_strategy_doc(strategy):
        raise ValueError("Not an AI Strategy")
    await cancel_open_startup_jobs(sid, reason=reason, jobs_repo=jobs_repo)
    return await jobs_repo.get_latest_for_strategy(sid)


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
            # Startup may use recent dailies when the week's open-day file is missing
            # (daily runner only writes "today", so Mon open-day often never exists).
            skip = await preview_weekly_brief_skip_reason(
                research, now, manual=True, relax_daily_prereqs=True
            )
            if _is_already_done_skip(skip):
                continue
            if skip is None:
                if kind not in task_ids:
                    task_id, err = await start_weekly_brief_task(
                        force=False, manual=True, relax_daily_prereqs=True
                    )
                    if err:
                        logger.info("Startup weekly brief start note: %s", err)
                    if task_id:
                        task_ids[kind] = task_id
                pending.append(kind)
                continue
            if _is_permanent_report_skip(skip):
                # Missing model / disabled / not scheduled — do not block startup forever.
                logger.info("Startup skipping weekly brief: %s", skip)
                if kind not in skipped:
                    skipped.append(kind)
                continue
            # Soft skips: keep waiting (e.g. today's daily still generating).
            pending.append(kind)
            continue

        if kind == REPORT_WEEKLY_DEBRIEF:
            skip = await preview_weekly_debrief_skip_reason(
                research, now, manual=True, relax_daily_prereqs=True
            )
            if _is_already_done_skip(skip):
                continue
            if skip is None:
                if kind not in task_ids:
                    task_id, err = await start_weekly_debrief_task(
                        force=False, manual=True, relax_daily_prereqs=True
                    )
                    if err:
                        logger.info("Startup weekly debrief start note: %s", err)
                    if task_id:
                        task_ids[kind] = task_id
                pending.append(kind)
                continue
            if _is_permanent_report_skip(skip):
                logger.info("Startup skipping weekly debrief: %s", skip)
                if kind not in skipped:
                    skipped.append(kind)
                continue
            # Soft waits (rare with relax) — keep pending.
            pending.append(kind)
            continue

    if pending:
        waiting = ", ".join(human_report_label(p) for p in pending)
        msg = f"Waiting for {waiting} to finish"
        if skipped:
            msg += f" (skipped {', '.join(human_report_label(s) for s in skipped)})"
        await jobs_repo.patch_doc(
            str(job["id"]),
            {
                "report_task_ids": task_ids,
                "skipped_reports": skipped,
                "phase": STARTUP_PHASE_ENSURING_REPORTS,
                "pending_reports": pending,
                **_progress_fields(
                    {**job, "phase": STARTUP_PHASE_ENSURING_REPORTS, "pending_reports": pending},
                    status_message=msg,
                ),
            },
        )
        return await jobs_repo.get_by_id(str(job["id"])) or job

    # Reports ready → move to seed phase.
    return await jobs_repo.patch_doc(
        str(job["id"]),
        {
            "phase": STARTUP_PHASE_SEEDING_DIGEST,
            "pending_reports": [],
            "report_task_ids": task_ids,
            "skipped_reports": skipped,
            **_progress_fields(
                {**job, "phase": STARTUP_PHASE_SEEDING_DIGEST, "pending_reports": []},
                status_message="Reports ready — seeding memory digest",
            ),
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
                "last_seed_wait": None,
                **_progress_fields(
                    {**job, "phase": STARTUP_PHASE_LOOPING},
                    status_message="Memory digest ready — starting improve loops",
                ),
            },
        ) or job

    # Mark seeding before the LLM call so the UI is not stuck on "reports".
    await jobs_repo.patch_doc(
        str(job["id"]),
        {
            "phase": STARTUP_PHASE_SEEDING_DIGEST,
            **_progress_fields(
                {**job, "phase": STARTUP_PHASE_SEEDING_DIGEST},
                status_message="Seeding memory digest from research…",
            ),
        },
    )

    try:
        digest = await seed_digest_from_research(str(job["strategy_id"]))
    except LlmBudgetExceeded as exc:
        reason = str(getattr(exc, "reason", "") or exc)
        # Another LLM call is in flight — keep the job running and retry next drain.
        if reason == "in_flight" or "in_flight" in reason.lower():
            logger.info(
                "Startup seed waiting on LLM in_flight strategy=%s",
                job.get("strategy_id"),
            )
            return (
                await jobs_repo.patch_doc(
                    str(job["id"]),
                    {
                        "phase": STARTUP_PHASE_SEEDING_DIGEST,
                        "last_seed_wait": f"budget_exceeded: {reason}",
                        **_progress_fields(
                            {
                                **job,
                                "phase": STARTUP_PHASE_SEEDING_DIGEST,
                                "last_seed_wait": f"budget_exceeded: {reason}",
                            },
                            status_message="Seeding paused — another LLM call is in flight; retrying soon",
                        ),
                    },
                )
                or job
            )
        return await jobs_repo.mark_failed(
            str(job["id"]), error=f"budget_exceeded: {reason}"
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
            "last_seed_wait": None,
            **_progress_fields(
                {
                    **job,
                    "phase": STARTUP_PHASE_LOOPING,
                    "seed_digest_version": digest.get("version"),
                    "loop_index": 0,
                },
                status_message="Memory seeded — starting improve loops",
            ),
        },
    ) or job


async def _start_backtest_if_needed(run_id: str) -> None:
    """Ensure a queued startup backtest is claimed by a *live* coordinator.

    Startup drain also runs in the orchestrator/secretary process, which may
    construct a BacktestCoordinator singleton that was never ``start()``-ed.
    Marking the run running there orphans it at 0% ("Starting backtest") because
    only the API process runs the claim loop. Leave the run queued when this
    process has no live coordinator so the API can claim it (auto_start or the
    next API drain notify).
    """
    runs = BacktestRunsRepository()
    run = await runs.get_by_id(run_id)
    if run is None:
        return

    try:
        from brokerai.backtesting.coordinator import get_backtest_coordinator

        coordinator = get_backtest_coordinator()
    except Exception:
        logger.exception("Failed to load backtest coordinator for startup run %s", run_id)
        return

    status = str(run.get("status") or "")
    if status == BACKTEST_RUN_STATUS_RUNNING:
        # Re-notify a live coordinator so secretary-orphaned runs get claimed.
        if coordinator.is_started:
            coordinator.notify_manual_start(run_id)
        return
    if status != BACKTEST_RUN_STATUS_QUEUED:
        return

    if not coordinator.is_started:
        logger.info(
            "Startup backtest %s left queued — coordinator not started in this process",
            run_id,
        )
        return

    updated = await runs.mark_running(run_id)
    if updated is None:
        return
    try:
        coordinator.notify_manual_start(run_id)
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
    loop_label = _loop_progress_label(loop_index, loop_target)
    mode = startup_loop_mode(loop_index)

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
            run_msg = str(run.get("status_message") or "").strip()
            verb = "pattern explore" if mode == LOOP_MODE_EXPLORE else "live-parity trade"
            msg = f"{loop_label} — {verb} {status}"
            if run_msg:
                msg = f"{msg} ({run_msg})"
            return (
                await jobs_repo.patch_doc(
                    str(job["id"]),
                    {
                        "phase": STARTUP_PHASE_LOOPING,
                        **_progress_fields(
                            {**job, "phase": STARTUP_PHASE_LOOPING},
                            status_message=msg,
                        ),
                    },
                )
                or job
            )
        if status in {BACKTEST_RUN_STATUS_FAILED, BACKTEST_RUN_STATUS_CANCELLED}:
            return await jobs_repo.mark_failed(
                str(job["id"]), error=f"startup backtest {status}: {current_run_id}"
            ) or job
        if status == BACKTEST_RUN_STATUS_COMPLETED:
            from brokerai.backtesting.ai_feedback import (
                AI_FEEDBACK_STATUS_COMPLETED,
                AI_FEEDBACK_STATUS_FAILED,
                AI_FEEDBACK_STATUS_RUNNING,
                normalize_ai_feedback,
                run_backtest_ai_feedback,
            )

            feedback = normalize_ai_feedback(
                run.get("ai_feedback") if isinstance(run.get("ai_feedback"), dict) else None
            )
            fb_status = str((feedback or {}).get("status") or "")

            # Another drain may already own / have finished memory feedback.
            if fb_status == AI_FEEDBACK_STATUS_RUNNING:
                return (
                    await jobs_repo.patch_doc(
                        str(job["id"]),
                        {
                            **_progress_fields(
                                {**job, "phase": STARTUP_PHASE_LOOPING},
                                status_message=(
                                    f"{loop_label} — waiting on memory feedback "
                                    "(another LLM call is in flight)"
                                ),
                            ),
                        },
                    )
                    or job
                )

            if fb_status not in {AI_FEEDBACK_STATUS_COMPLETED, AI_FEEDBACK_STATUS_FAILED}:
                await jobs_repo.patch_doc(
                    str(job["id"]),
                    {
                        **_progress_fields(
                            {**job, "phase": STARTUP_PHASE_LOOPING},
                            status_message=(
                                f"{loop_label} — writing "
                                f"{'pattern' if mode == LOOP_MODE_EXPLORE else 'trade'} "
                                "lessons to memory"
                            ),
                        ),
                    },
                )
                try:
                    await run_backtest_ai_feedback(str(current_run_id))
                except LlmBudgetExceeded as exc:
                    reason = str(getattr(exc, "reason", "") or exc)
                    if reason == "in_flight" or "in_flight" in reason.lower():
                        logger.info(
                            "Startup feedback waiting on LLM in_flight run=%s",
                            current_run_id,
                        )
                        return (
                            await jobs_repo.patch_doc(
                                str(job["id"]),
                                {
                                    "last_feedback_error": f"budget_exceeded: {reason}",
                                    **_progress_fields(
                                        {**job, "phase": STARTUP_PHASE_LOOPING},
                                        status_message=(
                                            f"{loop_label} — memory feedback paused "
                                            "(LLM in flight); retrying soon"
                                        ),
                                    ),
                                },
                            )
                            or job
                        )
                    logger.exception(
                        "Startup memory feedback budget denied run=%s strategy=%s",
                        current_run_id,
                        strategy_id,
                    )
                    await jobs_repo.patch_doc(
                        str(job["id"]),
                        {"last_feedback_error": f"budget_exceeded: {reason}"[:1000]},
                    )
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

                # Re-check: peer drain may still own the LLM call.
                refreshed = await runs_repo.get_by_id(str(current_run_id))
                feedback_after = normalize_ai_feedback(
                    refreshed.get("ai_feedback")
                    if isinstance((refreshed or {}).get("ai_feedback"), dict)
                    else None
                )
                after_status = str((feedback_after or {}).get("status") or "")
                if after_status == AI_FEEDBACK_STATUS_RUNNING:
                    return (
                        await jobs_repo.patch_doc(
                            str(job["id"]),
                            {
                                **_progress_fields(
                                    {**job, "phase": STARTUP_PHASE_LOOPING},
                                    status_message=(
                                        f"{loop_label} — waiting on memory feedback"
                                    ),
                                ),
                            },
                        )
                        or job
                    )

            next_index = loop_index + 1
            patched = await jobs_repo.advance_loop_after_run(
                str(job["id"]),
                expected_run_id=str(current_run_id),
                expected_loop_index=loop_index,
                next_loop_index=next_index,
                status_message=(
                    "Startup completed"
                    if next_index >= loop_target
                    else (
                        f"{loop_label} done — starting "
                        f"{_loop_progress_label(next_index, loop_target)}"
                    )
                ),
            )
            if patched is None:
                return job
            if next_index >= loop_target:
                return await jobs_repo.mark_completed(str(job["id"])) or patched
            return patched

    # Queue next loop (idempotent across API + secretary drain).
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
    mode_noun = "explore" if mode == LOOP_MODE_EXPLORE else "trade"
    cadence_key = f"startup:{strategy_id}:{job['id']}:{loop_index + 1}"
    existing = await runs_repo.find_by_cadence_key(cadence_key)
    created_new = False
    if existing is not None:
        run_id = str(existing.get("id") or "")
    else:
        created = await runs_repo.create_queued_runs(
            [compiled],
            name=(
                f"{strategy.get('name') or 'AI Strategy'} startup {mode_noun} "
                f"{loop_index + 1}/{loop_target}"
            ),
            period=period,
            origin=ORIGIN_AI_STRATEGY_STARTUP,
            cadence_key=cadence_key,
            digest_version=digest_version,
            loop_mode=mode,
        )
        if not created:
            return await jobs_repo.mark_failed(
                str(job["id"]), error="failed to queue startup backtest"
            ) or job
        run_id = str(created[0].get("id") or "")
        created_new = True
        # Another drain may have created the same cadence a moment earlier.
        winner = await runs_repo.find_by_cadence_key(cadence_key)
        if winner is not None and str(winner.get("id") or "") != run_id:
            try:
                await runs_repo.request_cancel(run_id)
            except Exception:
                logger.warning(
                    "Failed to cancel duplicate startup run %s cadence=%s",
                    run_id,
                    cadence_key,
                    exc_info=True,
                )
            run_id = str(winner.get("id") or "")
            created_new = False

    if not run_id:
        return await jobs_repo.mark_failed(
            str(job["id"]), error="failed to resolve startup backtest id"
        ) or job

    queued_verb = (
        "pattern explore queued" if mode == LOOP_MODE_EXPLORE else "live-parity trade queued"
    )
    attached = await jobs_repo.attach_current_run_if_absent(
        str(job["id"]),
        loop_index=loop_index,
        run_id=run_id,
        status_message=f"{loop_label} — {queued_verb}",
    )
    if attached is None:
        return job
    attached_run = str(attached.get("current_backtest_run_id") or "")
    if attached_run and attached_run != run_id:
        # Lost the attach race — keep the winner, cancel our duplicate if we made one.
        if created_new:
            try:
                await runs_repo.request_cancel(run_id)
            except Exception:
                logger.warning(
                    "Failed to cancel unattached startup run %s",
                    run_id,
                    exc_info=True,
                )
        run_id = attached_run
    elif not attached_run:
        # Loop index moved or job closed while we queued.
        if created_new:
            try:
                await runs_repo.request_cancel(run_id)
            except Exception:
                logger.warning(
                    "Failed to cancel abandoned startup run %s",
                    run_id,
                    exc_info=True,
                )
        return attached

    await _start_backtest_if_needed(run_id)
    return attached


async def advance_startup_job(job_id: str) -> dict[str, Any] | None:
    """Advance one startup job by a single drain step."""
    jobs_repo = AiStrategyStartupJobsRepository()
    job = await jobs_repo.get_by_id(job_id)
    if job is None:
        return None
    if job.get("status") in {
        STARTUP_STATUS_COMPLETED,
        STARTUP_STATUS_FAILED,
        STARTUP_STATUS_CANCELLED,
    }:
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
