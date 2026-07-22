"""Human-readable AI Strategy startup progress for jobs + activity log."""

from __future__ import annotations

from typing import Any

REPORT_LABELS = {
    "daily_report": "daily report",
    "weekly_brief": "weekly brief",
    "weekly_debrief": "weekly debrief",
}

PHASE_TITLES = {
    "ensuring_reports": "Startup · reports",
    "seeding_digest": "Startup · seeding memory",
    "looping": "Startup · improve loops",
    "done": "Startup completed",
}


def human_report_label(kind: str) -> str:
    key = (kind or "").strip()
    return REPORT_LABELS.get(key, key.replace("_", " ") or "report")


def build_startup_status_message(job: dict[str, Any] | None) -> str:
    """Short operator-facing status for tags and the Startup card."""
    if not job:
        return "No startup job"
    status = str(job.get("status") or "")
    if status == "failed":
        return str(job.get("error") or "Startup failed")
    if status == "cancelled":
        return str(job.get("error") or "Startup cancelled")
    if status == "completed":
        return "Startup completed"
    if status == "queued":
        return "Startup queued — waiting for drain"

    # Prefer an explicit message written by the drain loop.
    explicit = str(job.get("status_message") or "").strip()
    if explicit:
        return explicit

    phase = str(job.get("phase") or "")
    pending = [str(p) for p in (job.get("pending_reports") or []) if p]
    if phase == "ensuring_reports":
        if pending:
            labels = ", ".join(human_report_label(p) for p in pending)
            return f"Waiting for {labels}"
        return "Checking research reports"
    if phase == "seeding_digest":
        wait = str(job.get("last_seed_wait") or "").strip()
        if wait:
            return f"Seeding memory — {wait}"
        return "Seeding memory digest from research"
    if phase == "looping":
        loop_index = int(job.get("loop_index") or 0)
        loop_target = int(job.get("loop_target") or 0)
        mode = "explore" if loop_index <= 0 else "trade"
        mode_label = "Explore" if mode == "explore" else "Trade"
        if job.get("current_backtest_run_id"):
            if loop_target > 0:
                return (
                    f"{mode_label} loop {min(loop_index + 1, loop_target)}/{loop_target} "
                    "— in progress"
                )
            return f"{mode_label} loop in progress"
        if loop_target > 0:
            return (
                f"Starting {mode_label.lower()} loop "
                f"{min(loop_index + 1, loop_target)}/{loop_target}"
            )
        return "Running improve loops"
    return PHASE_TITLES.get(phase, "Startup running")


def build_startup_event_title(job: dict[str, Any] | None) -> str:
    """Activity-log title that reflects the active phase (not a generic 'running')."""
    if not job:
        return "Startup"
    status = str(job.get("status") or "")
    if status == "failed":
        return "Startup failed"
    if status == "cancelled":
        return "Startup cancelled"
    if status == "completed":
        return "Startup completed"
    if status == "queued":
        return "Startup queued"

    phase = str(job.get("phase") or "")
    pending = [str(p) for p in (job.get("pending_reports") or []) if p]
    if phase == "ensuring_reports" and pending:
        return f"Startup · waiting on {human_report_label(pending[0])}"
    if phase == "seeding_digest":
        if job.get("last_seed_wait"):
            return "Startup · seeding (waiting on LLM)"
        return "Startup · seeding memory"
    if phase == "looping":
        loop_index = int(job.get("loop_index") or 0)
        loop_target = int(job.get("loop_target") or 0)
        mode_label = "explore" if loop_index <= 0 else "trade"
        if loop_target > 0:
            return (
                f"Startup · {mode_label} "
                f"{min(loop_index + 1, loop_target)}/{loop_target}"
            )
        return "Startup · improve loops"
    return PHASE_TITLES.get(phase, "Startup running")


def build_startup_event_detail(job: dict[str, Any] | None) -> str:
    """Short detail line for the activity feed (avoid report laundry lists)."""
    if not job:
        return ""
    message = build_startup_status_message(job)
    skipped = [str(r) for r in (job.get("skipped_reports") or []) if r]
    if skipped and str(job.get("phase") or "") == "ensuring_reports":
        skip_text = ", ".join(human_report_label(r) for r in skipped)
        if message and skip_text.lower() not in message.lower():
            return f"{message} · skipped {skip_text}"
    return message
