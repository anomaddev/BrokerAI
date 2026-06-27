"""Research background task adapters."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from brokerai.activity.constants import (
    ACTION_DAILY_REPORT_COMPLETED,
    ACTION_DAILY_REPORT_FAILED,
    ACTION_WEEKLY_BRIEF_COMPLETED,
    ACTION_WEEKLY_DEBRIEF_COMPLETED,
)
from brokerai.activity.log import record_bot_activity
from brokerai.bots.researcher.runner import (
    RunResult,
    run_daily_report,
    run_daily_report_result_payload,
)
from brokerai.bots.researcher.weekly import (
    WeeklyRunResult,
    run_weekly_brief,
    run_weekly_debrief,
    weekly_run_result_payload,
)
from brokerai.tasks.cancellation import CancellationToken
from brokerai.tasks.kinds import RESEARCH_KINDS, ResearchKind, task_kind_spec
from brokerai.tasks.runner import (
    finish_task_failed,
    finish_task_skipped,
    finish_task_success,
    make_progress_callback,
    start_task,
    update_task,
)

logger = logging.getLogger(__name__)

ResearchRunner = Callable[..., Awaitable[RunResult | WeeklyRunResult]]
PayloadFn = Callable[[Any], dict]


async def _execute_run_result(
    kind: str,
    result: RunResult | WeeklyRunResult,
    payload_fn: PayloadFn,
    *,
    record_activity: bool,
) -> None:
    payload = payload_fn(result)
    spec = task_kind_spec(kind)
    label = spec.label if spec else kind
    today = datetime.now(timezone.utc).date().isoformat()

    if result.skipped_reason:
        await finish_task_skipped(result.skipped_reason, result=payload)
        return

    if not result.ok:
        error = "; ".join(result.errors) if result.errors else f"{label} failed"
        await finish_task_failed(error)
        if record_activity and kind in ("research_daily", "research_daily_rerun"):
            await record_bot_activity(
                ACTION_DAILY_REPORT_FAILED,
                "Daily report failed",
                detail=error,
                source="researcher",
                metadata={"report_date": today},
            )
        return

    message = f"{label} ready"
    await finish_task_success(payload, message=message)

    if not record_activity:
        return

    if kind in ("research_daily", "research_daily_rerun") and result.report_path:
        await record_bot_activity(
            ACTION_DAILY_REPORT_COMPLETED,
            "Daily report",
            detail=f"Completed for {today}",
            source="researcher",
            metadata={"report_path": result.report_path, "report_date": today},
        )
    elif kind == "research_weekly_brief" and result.report_path:
        await record_bot_activity(
            ACTION_WEEKLY_BRIEF_COMPLETED,
            "Weekly brief",
            detail=f"Completed for {result.week_key or 'current week'}",
            source="researcher",
            metadata={"report_path": result.report_path, "week_key": result.week_key},
        )
    elif kind == "research_weekly_debrief" and result.report_path:
        await record_bot_activity(
            ACTION_WEEKLY_DEBRIEF_COMPLETED,
            "Weekly debrief",
            detail=f"Completed for {result.week_key or 'completed week'}",
            source="researcher",
            metadata={"report_path": result.report_path, "week_key": result.week_key},
        )


def _progress_wrapped(on_progress: Callable[[str, str, int], None], token: CancellationToken):
    def callback(step: str, message: str, progress: int) -> None:
        token.check()
        on_progress(step, message, progress)

    return callback


async def start_research_task(
    kind: ResearchKind,
    *,
    force: bool,
    manual: bool,
    start_message: str | None = None,
) -> tuple[str | None, str | None]:
    spec = task_kind_spec(kind)
    if spec is None:
        return None, f"Unknown research task kind: {kind}"

    if kind in ("research_daily", "research_daily_rerun"):
        runner_fn: ResearchRunner = run_daily_report
        payload_fn = run_daily_report_result_payload
        default_message = "Starting daily report…" if kind == "research_daily" else "Re-running daily report…"
    elif kind == "research_weekly_brief":
        runner_fn = run_weekly_brief
        payload_fn = weekly_run_result_payload
        default_message = "Starting weekly brief…"
    elif kind == "research_weekly_debrief":
        runner_fn = run_weekly_debrief
        payload_fn = weekly_run_result_payload
        default_message = "Starting weekly debrief…"
    else:
        return None, f"Unsupported research kind: {kind}"

    message = start_message or default_message

    async def work(token: CancellationToken) -> None:
        update_task("start", message, 5)
        token.check()
        on_progress = _progress_wrapped(make_progress_callback(), token)
        result = await runner_fn(force=force, manual=manual, on_progress=on_progress)
        await _execute_run_result(kind, result, payload_fn, record_activity=True)

    return await start_task(
        kind,
        spec.label,
        work,
        exclusive_kinds=RESEARCH_KINDS,
    )


async def start_daily_report_task(*, force: bool, manual: bool) -> tuple[str | None, str | None]:
    return await start_research_task("research_daily", force=force, manual=manual)


async def start_daily_rerun_task(*, force: bool = True) -> tuple[str | None, str | None]:
    return await start_research_task("research_daily_rerun", force=force, manual=True)


async def start_weekly_brief_task(*, force: bool, manual: bool) -> tuple[str | None, str | None]:
    return await start_research_task("research_weekly_brief", force=force, manual=manual)


async def start_weekly_debrief_task(*, force: bool, manual: bool) -> tuple[str | None, str | None]:
    return await start_research_task("research_weekly_debrief", force=force, manual=manual)


async def start_scheduled_daily_task() -> tuple[str | None, str | None]:
    return await start_research_task(
        "research_daily",
        force=False,
        manual=False,
        start_message="Running scheduled daily report…",
    )


async def start_scheduled_weekly_brief_task() -> tuple[str | None, str | None]:
    return await start_research_task(
        "research_weekly_brief",
        force=False,
        manual=False,
        start_message="Running scheduled weekly brief…",
    )


async def start_scheduled_weekly_debrief_task() -> tuple[str | None, str | None]:
    return await start_research_task(
        "research_weekly_debrief",
        force=False,
        manual=False,
        start_message="Running scheduled weekly debrief…",
    )
