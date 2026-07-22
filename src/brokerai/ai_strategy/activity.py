"""Aggregate AI Strategy activity into a newest-first log timeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from brokerai.ai_strategy.lifecycle import is_ai_strategy_doc
from brokerai.ai_strategy.startup_status import (
    build_startup_event_detail,
    build_startup_event_title,
    build_startup_status_message,
)
from brokerai.db.repositories.ai_strategy_startup import (
    STARTUP_OPEN_STATUSES,
    AiStrategyStartupJobsRepository,
)
from brokerai.db.repositories.backtest_runs import (
    BACKTEST_RUN_STATUS_QUEUED,
    BACKTEST_RUN_STATUS_RUNNING,
    BacktestRunsRepository,
)
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.db.repositories.strategy_learning import (
    LEARNING_JOB_OPEN_STATUSES,
    LearningJobsRepository,
    StrategyMemoryDigestsRepository,
)
from brokerai.db.repositories.strategy_versions import StrategyVersionsRepository

ORIGIN_LABELS = {
    "ai_strategy_startup": "Startup improve",
    "ai_strategy_daily": "Daily improve",
}

def _parse_iso(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _iso(raw: Any) -> str | None:
    parsed = _parse_iso(raw)
    return parsed.isoformat() if parsed else None


def _event(
    *,
    event_id: str,
    kind: str,
    title: str,
    occurred_at: Any,
    status: str = "info",
    detail: str | None = None,
    href: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    when = _iso(occurred_at)
    if not when:
        return None
    return {
        "id": event_id,
        "kind": kind,
        "status": status,
        "title": title,
        "detail": detail,
        "occurred_at": when,
        "href": href,
        "meta": meta or {},
    }


def _events_from_startup(job: dict[str, Any]) -> list[dict[str, Any]]:
    job_id = str(job.get("id") or "")
    status = str(job.get("status") or "")
    events: list[dict[str, Any]] = []
    detail = build_startup_event_detail(job)

    queued = _event(
        event_id=f"startup:{job_id}:queued",
        kind="startup",
        status="queued",
        title="Startup queued",
        detail="Create-time sequence: reports → seed digest → improve loops",
        occurred_at=job.get("created_at"),
        meta={"job_id": job_id, "phase": job.get("phase")},
    )
    if queued:
        events.append(queued)

    if status in STARTUP_OPEN_STATUSES and (job.get("started_at") or status == "queued"):
        # Use updated_at so the live row stays near the top of newest-first logs.
        when = job.get("updated_at") or job.get("started_at") or job.get("created_at")
        running = _event(
            event_id=f"startup:{job_id}:progress",
            kind="startup",
            status="running" if job.get("started_at") else "queued",
            title=build_startup_event_title(job),
            detail=detail,
            occurred_at=when,
            meta={
                "job_id": job_id,
                "phase": job.get("phase"),
                "status_message": build_startup_status_message(job),
                "pending_reports": list(job.get("pending_reports") or []),
            },
        )
        if running:
            events.append(running)

    if status == "completed" and job.get("finished_at"):
        done = _event(
            event_id=f"startup:{job_id}:completed",
            kind="startup",
            status="completed",
            title="Startup completed",
            detail=detail,
            occurred_at=job.get("finished_at"),
            meta={"job_id": job_id},
        )
        if done:
            events.append(done)
    elif status == "failed" and job.get("finished_at"):
        failed = _event(
            event_id=f"startup:{job_id}:failed",
            kind="startup",
            status="failed",
            title="Startup failed",
            detail=str(job.get("error") or "Unknown error"),
            occurred_at=job.get("finished_at"),
            meta={"job_id": job_id},
        )
        if failed:
            events.append(failed)
    elif status == "cancelled" and job.get("finished_at"):
        cancelled = _event(
            event_id=f"startup:{job_id}:cancelled",
            kind="startup",
            status="cancelled",
            title="Startup cancelled",
            detail=detail,
            occurred_at=job.get("finished_at"),
            meta={"job_id": job_id},
        )
        if cancelled:
            events.append(cancelled)
    elif status in STARTUP_OPEN_STATUSES and not job.get("started_at"):
        if events:
            events[0]["detail"] = detail
            events[0]["title"] = build_startup_event_title(job)
            events[0]["meta"]["phase"] = job.get("phase")

    return events


def _origin_label(origin: str | None) -> str:
    text = (origin or "").strip()
    if not text:
        return "Backtest"
    return ORIGIN_LABELS.get(text, text.replace("_", " ").title())


def _is_ai_strategy_backtest_origin(origin: str | None) -> bool:
    text = (origin or "").strip()
    return text in {"ai_strategy_startup", "ai_strategy_daily"}


def _events_from_backtest(run: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = str(run.get("id") or "")
    status = str(run.get("status") or "")
    origin = str(run.get("origin") or "") or None
    instrument = str(run.get("instrument") or (run.get("instruments") or [None])[0] or "")
    digest = run.get("digest_version")
    href = f"/research/backtest/{run_id}" if run_id else None
    signal_review = _is_ai_strategy_backtest_origin(origin)
    detail_parts = [
        _origin_label(origin),
        instrument or None,
        f"Period {run.get('period')}" if run.get("period") else None,
        f"Digest v{digest}" if digest not in (None, "") else None,
    ]
    if status in {BACKTEST_RUN_STATUS_QUEUED, BACKTEST_RUN_STATUS_RUNNING}:
        msg = run.get("status_message")
        if msg:
            detail_parts.append(str(msg))
    elif status == "completed":
        if signal_review:
            # AI Strategy improve loops are signal/trend reviews, not P&L scorecards.
            params = run.get("params_snapshot") if isinstance(run.get("params_snapshot"), dict) else {}
            signal = params.get("signal") if isinstance(params.get("signal"), dict) else {}
            bias = str(signal.get("bias") or "").strip()
            if bias:
                detail_parts.append(f"Bias {bias}")
            feedback = run.get("ai_feedback") if isinstance(run.get("ai_feedback"), dict) else None
            if feedback:
                notes = feedback.get("memory_notes") or []
                if notes:
                    detail_parts.append(f"{len(notes)} signal lesson(s)")
                elif feedback.get("status"):
                    detail_parts.append(f"Review {feedback.get('status')}")
        else:
            stats = run.get("stats") or {}
            trades = stats.get("total_trades")
            pnl = stats.get("realized_pnl")
            if trades is not None:
                detail_parts.append(f"{trades} trades")
            if pnl is not None:
                detail_parts.append(f"P&L {float(pnl):+.2f}")
            feedback = run.get("ai_feedback") if isinstance(run.get("ai_feedback"), dict) else None
            if feedback:
                notes = feedback.get("memory_notes") or []
                if notes:
                    detail_parts.append(f"{len(notes)} memory note(s)")
                elif feedback.get("status"):
                    detail_parts.append(f"Feedback {feedback.get('status')}")
    elif status == "failed" and run.get("error"):
        detail_parts.append(str(run["error"]))

    detail = " · ".join(str(p) for p in detail_parts if p)
    when = run.get("finished_at") or run.get("started_at") or run.get("created_at")
    if signal_review:
        title = {
            BACKTEST_RUN_STATUS_QUEUED: "Signal review queued",
            BACKTEST_RUN_STATUS_RUNNING: "Signal review running",
            "completed": "Signal review completed",
            "failed": "Signal review failed",
            "cancelled": "Signal review cancelled",
        }.get(status, f"Signal review {status or 'updated'}")
    else:
        title = {
            BACKTEST_RUN_STATUS_QUEUED: "Backtest queued",
            BACKTEST_RUN_STATUS_RUNNING: "Backtest running",
            "completed": "Backtest completed",
            "failed": "Backtest failed",
            "cancelled": "Backtest cancelled",
        }.get(status, f"Backtest {status or 'updated'}")

    event = _event(
        event_id=f"backtest:{run_id}:{status or 'updated'}",
        kind="backtest",
        status=status or "info",
        title=title,
        detail=detail or None,
        occurred_at=when,
        href=href,
        meta={"run_id": run_id, "origin": origin, "instrument": instrument},
    )
    return [event] if event else []


def _events_from_digest(digest: dict[str, Any]) -> list[dict[str, Any]]:
    digest_id = str(digest.get("id") or "")
    version = digest.get("version")
    source = str(digest.get("source") or "")
    standing = list(digest.get("standing_rules") or [])
    anti = list(digest.get("anti_rules") or [])
    summary = str(digest.get("summary") or "").strip()
    source_label = {
        "ai_strategy_startup_seed": "Research-seeded digest",
        "ai_strategy_daily_feedback": "Backtest feedback digest",
        "strategy_learn": "Outcome learning digest",
    }.get(source, "Memory digest")
    detail_parts = [
        f"v{version}" if version is not None else None,
        source_label,
        f"{len(standing)} standing / {len(anti)} anti rules",
        summary[:160] if summary else None,
    ]
    event = _event(
        event_id=f"digest:{digest_id}:v{version}",
        kind="digest",
        status="completed",
        title="Memory digest updated",
        detail=" · ".join(str(p) for p in detail_parts if p),
        occurred_at=digest.get("created_at"),
        meta={"digest_id": digest_id, "version": version, "source": source},
    )
    return [event] if event else []


def _events_from_learning(job: dict[str, Any]) -> list[dict[str, Any]]:
    job_id = str(job.get("id") or "")
    status = str(job.get("status") or "")
    when = job.get("finished_at") or job.get("started_at") or job.get("created_at")
    detail_parts = [
        f"Digest v{job['digest_version']}" if job.get("digest_version") is not None else None,
        str(job.get("error") or "") if status == "failed" else None,
    ]
    title = {
        "queued": "Learning queued",
        "running": "Learning from outcomes",
        "completed": "Learning completed",
        "failed": "Learning failed",
    }.get(status, "Learning job")
    event = _event(
        event_id=f"learning:{job_id}:{status or 'updated'}",
        kind="learning",
        status=status or "info",
        title=title,
        detail=" · ".join(p for p in detail_parts if p) or None,
        occurred_at=when,
        meta={"job_id": job_id},
    )
    return [event] if event else []


def _events_from_lifecycle(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    warmup = strategy.get("warmup") if isinstance(strategy.get("warmup"), dict) else {}
    events: list[dict[str, Any]] = []
    sid = str(strategy.get("id") or "")
    ready_at = warmup.get("ready_at")
    if ready_at:
        event = _event(
            event_id=f"lifecycle:{sid}:ready",
            kind="lifecycle",
            status="completed",
            title="Warm-up complete — ready to promote",
            detail="Shadow trading finished its target ET days",
            occurred_at=ready_at,
        )
        if event:
            events.append(event)
    live_at = warmup.get("live_at")
    if live_at:
        event = _event(
            event_id=f"lifecycle:{sid}:live",
            kind="lifecycle",
            status="completed",
            title="Promoted to live",
            detail="Strategy may dispatch live trades",
            occurred_at=live_at,
        )
        if event:
            events.append(event)
    return events


def _events_from_version(version: dict[str, Any]) -> list[dict[str, Any]]:
    version_id = str(version.get("id") or "")
    label = str(version.get("change_label") or "Parameters updated").strip()
    ver = version.get("version")
    # Skip the initial create noise; the startup sequence covers creation.
    if ver == 1 and label.lower().startswith("created"):
        return []
    event = _event(
        event_id=f"version:{version_id}",
        kind="version",
        status="info",
        title="Parameters updated",
        detail=f"v{ver} · {label}" if ver is not None else label,
        occurred_at=version.get("created_at"),
        meta={"version_id": version_id, "version": ver},
    )
    return [event] if event else []


def _rule_texts(raw: Any, *, limit: int = 8) -> list[str]:
    """Normalize digest rules to plain strings for the activity API.

    Digests store rules as ``{"kind": "...", "text": "..."}`` (preferred) or
    legacy bare strings. The Log UI renders text nodes, so object payloads must
    never leak through.
    """
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            continue
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _digest_summary(digest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not digest:
        return None
    standing = list(digest.get("standing_rules") or [])
    anti = list(digest.get("anti_rules") or [])
    return {
        "id": digest.get("id"),
        "version": digest.get("version"),
        "created_at": digest.get("created_at"),
        "source": digest.get("source"),
        "summary": digest.get("summary"),
        "standing_rule_count": len(standing),
        "anti_rule_count": len(anti),
        "standing_rules": _rule_texts(standing, limit=8),
        "anti_rules": _rule_texts(anti, limit=8),
    }


def _sort_key(event: dict[str, Any]) -> datetime:
    return _parse_iso(event.get("occurred_at")) or datetime.min.replace(tzinfo=timezone.utc)


async def build_ai_strategy_activity(
    strategy_id: str,
    *,
    limit: int = 50,
) -> dict[str, Any] | None:
    """Return strategy snapshot + newest-first activity events.

    Returns ``None`` when the strategy id does not exist.
    Raises ``ValueError`` when the strategy is not an AI Strategy.
    """
    sid = (strategy_id or "").strip()
    if not sid:
        return None

    strategy = await StrategiesRepository().get_by_id(sid)
    if strategy is None:
        return None
    if not is_ai_strategy_doc(strategy):
        raise ValueError("Not an AI Strategy")

    limit = max(1, min(int(limit), 100))
    fetch_n = max(limit, 20)

    startup_jobs = await AiStrategyStartupJobsRepository().list_for_strategy(sid, limit=10)
    backtests = await BacktestRunsRepository().list_runs(strategy_id=sid, limit=fetch_n)
    digests = await StrategyMemoryDigestsRepository().list_for_strategy(sid, limit=fetch_n)
    learning_jobs = await LearningJobsRepository().list_for_strategy(sid, limit=fetch_n)
    versions, _total = await StrategyVersionsRepository().list_for_strategy(sid, limit=15)

    events: list[dict[str, Any]] = []
    for job in startup_jobs:
        events.extend(_events_from_startup(job))
    for run in backtests:
        events.extend(_events_from_backtest(run))
    for digest in digests:
        events.extend(_events_from_digest(digest))
    for job in learning_jobs:
        events.extend(_events_from_learning(job))
    events.extend(_events_from_lifecycle(strategy))
    for version in versions:
        events.extend(_events_from_version(version))

    events.sort(key=_sort_key, reverse=True)
    events = events[:limit]

    latest_startup = startup_jobs[0] if startup_jobs else None
    latest_digest = digests[0] if digests else None

    active = False
    if latest_startup and str(latest_startup.get("status") or "") in STARTUP_OPEN_STATUSES:
        active = True
    if any(
        str(run.get("status") or "") in {BACKTEST_RUN_STATUS_QUEUED, BACKTEST_RUN_STATUS_RUNNING}
        for run in backtests
    ):
        active = True
    if any(str(job.get("status") or "") in LEARNING_JOB_OPEN_STATUSES for job in learning_jobs):
        active = True

    return {
        "strategy": strategy,
        "startup_job": latest_startup,
        "latest_digest": _digest_summary(latest_digest),
        "events": events,
        "active": active,
    }
