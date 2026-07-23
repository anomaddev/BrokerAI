"""Repositories for durable AI Strategy startup jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import AiStrategyStartupJobRow

STARTUP_STATUS_QUEUED = "queued"
STARTUP_STATUS_RUNNING = "running"
STARTUP_STATUS_COMPLETED = "completed"
STARTUP_STATUS_FAILED = "failed"
STARTUP_STATUS_CANCELLED = "cancelled"

STARTUP_OPEN_STATUSES = frozenset({STARTUP_STATUS_QUEUED, STARTUP_STATUS_RUNNING})

STARTUP_PHASE_ENSURING_REPORTS = "ensuring_reports"
STARTUP_PHASE_SEEDING_DIGEST = "seeding_digest"
STARTUP_PHASE_LOOPING = "looping"
STARTUP_PHASE_DONE = "done"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AiStrategyStartupJobsRepository:
    """Queued/running create-time startup workflows."""

    async def enqueue(self, strategy_id: str, doc: dict[str, Any] | None = None) -> dict[str, Any]:
        job_id = str((doc or {}).get("id") or uuid4().hex)
        created = _now()
        payload = {
            **(doc or {}),
            "id": job_id,
            "strategy_id": strategy_id,
            "status": STARTUP_STATUS_QUEUED,
            "phase": STARTUP_PHASE_ENSURING_REPORTS,
            "loop_index": int((doc or {}).get("loop_index") or 0),
            "loop_target": int((doc or {}).get("loop_target") or 3),
            "required_reports": list((doc or {}).get("required_reports") or []),
            "report_task_ids": dict((doc or {}).get("report_task_ids") or {}),
            "skipped_reports": list((doc or {}).get("skipped_reports") or []),
            "current_backtest_run_id": (doc or {}).get("current_backtest_run_id"),
            "seed_digest_version": (doc or {}).get("seed_digest_version"),
            "error": None,
            "created_at": created.isoformat(),
        }
        async with session_scope() as session:
            session.add(
                AiStrategyStartupJobRow(
                    id=job_id,
                    strategy_id=strategy_id,
                    status=STARTUP_STATUS_QUEUED,
                    phase=STARTUP_PHASE_ENSURING_REPORTS,
                    created_at=created,
                    started_at=None,
                    finished_at=None,
                    doc=payload,
                )
            )
        return payload

    async def get_by_id(self, job_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(AiStrategyStartupJobRow, job_id)
            if row is None:
                return None
            return self._serialize(row)

    async def get_latest_for_strategy(self, strategy_id: str) -> dict[str, Any] | None:
        sid = (strategy_id or "").strip()
        if not sid:
            return None
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(AiStrategyStartupJobRow)
                    .where(AiStrategyStartupJobRow.strategy_id == sid)
                    .order_by(AiStrategyStartupJobRow.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return self._serialize(row)

    async def has_open_job(self, strategy_id: str) -> bool:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(AiStrategyStartupJobRow.id)
                    .where(
                        AiStrategyStartupJobRow.strategy_id == strategy_id,
                        AiStrategyStartupJobRow.status.in_(tuple(STARTUP_OPEN_STATUSES)),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            return row is not None

    async def list_open_for_strategy(
        self,
        strategy_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return open (queued/running) startup jobs for one strategy, oldest first."""
        sid = (strategy_id or "").strip()
        if not sid:
            return []
        limit = max(1, min(int(limit), 100))
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(AiStrategyStartupJobRow)
                    .where(
                        AiStrategyStartupJobRow.strategy_id == sid,
                        AiStrategyStartupJobRow.status.in_(tuple(STARTUP_OPEN_STATUSES)),
                    )
                    .order_by(AiStrategyStartupJobRow.created_at.asc())
                    .limit(limit)
                )
            ).scalars().all()
            return [self._serialize(row) for row in rows]

    async def list_open(self, *, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(AiStrategyStartupJobRow)
                    .where(AiStrategyStartupJobRow.status.in_(tuple(STARTUP_OPEN_STATUSES)))
                    .order_by(AiStrategyStartupJobRow.created_at.asc())
                    .limit(limit)
                )
            ).scalars().all()
            return [self._serialize(row) for row in rows]

    async def list_for_strategy(
        self,
        strategy_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return startup jobs for a strategy (newest first)."""
        sid = (strategy_id or "").strip()
        if not sid:
            return []
        limit = max(1, min(int(limit), 100))
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(AiStrategyStartupJobRow)
                    .where(AiStrategyStartupJobRow.strategy_id == sid)
                    .order_by(AiStrategyStartupJobRow.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return [self._serialize(row) for row in rows]

    async def mark_running(self, job_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(AiStrategyStartupJobRow, job_id)
            if row is None:
                return None
            if row.status not in STARTUP_OPEN_STATUSES:
                return self._serialize(row)
            started = row.started_at or _now()
            doc = dict(row.doc)
            doc["status"] = STARTUP_STATUS_RUNNING
            doc["started_at"] = started.isoformat()
            row.status = STARTUP_STATUS_RUNNING
            row.started_at = started
            row.doc = doc
            return self._serialize(row)

    async def patch_doc(self, job_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(AiStrategyStartupJobRow, job_id)
            if row is None:
                return None
            doc = dict(row.doc)
            doc.update(patch)
            if "phase" in patch:
                row.phase = str(patch["phase"])
                doc["phase"] = row.phase
            if "status" in patch:
                row.status = str(patch["status"])
                doc["status"] = row.status
            row.doc = doc
            return self._serialize(row)

    async def attach_current_run_if_absent(
        self,
        job_id: str,
        *,
        loop_index: int,
        run_id: str,
        status_message: str | None = None,
    ) -> dict[str, Any] | None:
        """Atomically attach ``run_id`` when this loop still has no current run.

        Returns the job after the write. When another drain already attached a
        run for this loop, returns that job unchanged (``current_backtest_run_id``
        may differ from ``run_id``) so the loser can cancel its duplicate.
        Returns ``None`` only when the job is missing or no longer open.
        """
        rid = (run_id or "").strip()
        if not rid:
            return None
        async with session_scope() as session:
            row = await session.get(
                AiStrategyStartupJobRow, job_id, with_for_update=True
            )
            if row is None:
                return None
            if row.status not in STARTUP_OPEN_STATUSES:
                return self._serialize(row)
            doc = dict(row.doc)
            current_index = int(doc.get("loop_index") or 0)
            if current_index != int(loop_index):
                # Stale drain tick — another process already advanced the loop.
                return self._serialize(row)
            existing = doc.get("current_backtest_run_id")
            if existing:
                return self._serialize(row)
            doc["current_backtest_run_id"] = rid
            doc["phase"] = STARTUP_PHASE_LOOPING
            doc["loop_index"] = int(loop_index)
            doc["updated_at"] = _now().isoformat()
            if status_message is not None:
                doc["status_message"] = status_message
            row.phase = STARTUP_PHASE_LOOPING
            row.doc = doc
            return self._serialize(row)

    async def advance_loop_after_run(
        self,
        job_id: str,
        *,
        expected_run_id: str,
        expected_loop_index: int,
        next_loop_index: int,
        status_message: str | None = None,
    ) -> dict[str, Any] | None:
        """Clear the finished run and bump ``loop_index`` only once.

        Prevents API + secretary drain from both advancing the same completed
        loop (which previously queued a second backtest for the next index).
        """
        expected = (expected_run_id or "").strip()
        if not expected:
            return None
        async with session_scope() as session:
            row = await session.get(
                AiStrategyStartupJobRow, job_id, with_for_update=True
            )
            if row is None:
                return None
            if row.status not in STARTUP_OPEN_STATUSES:
                return self._serialize(row)
            doc = dict(row.doc)
            if str(doc.get("current_backtest_run_id") or "") != expected:
                return self._serialize(row)
            if int(doc.get("loop_index") or 0) != int(expected_loop_index):
                return self._serialize(row)
            doc["loop_index"] = int(next_loop_index)
            doc["current_backtest_run_id"] = None
            doc["phase"] = STARTUP_PHASE_LOOPING
            doc["updated_at"] = _now().isoformat()
            if status_message is not None:
                doc["status_message"] = status_message
            row.phase = STARTUP_PHASE_LOOPING
            row.doc = doc
            return self._serialize(row)

    async def mark_completed(self, job_id: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(AiStrategyStartupJobRow, job_id)
            if row is None:
                return None
            finished = _now()
            doc = dict(row.doc)
            doc["status"] = STARTUP_STATUS_COMPLETED
            doc["phase"] = STARTUP_PHASE_DONE
            doc["finished_at"] = finished.isoformat()
            doc["error"] = None
            if extra:
                doc.update(extra)
            row.status = STARTUP_STATUS_COMPLETED
            row.phase = STARTUP_PHASE_DONE
            row.finished_at = finished
            row.doc = doc
            return self._serialize(row)

    async def mark_failed(self, job_id: str, *, error: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(AiStrategyStartupJobRow, job_id)
            if row is None:
                return None
            finished = _now()
            doc = dict(row.doc)
            doc["status"] = STARTUP_STATUS_FAILED
            doc["finished_at"] = finished.isoformat()
            doc["error"] = (error or "unknown")[:2000]
            row.status = STARTUP_STATUS_FAILED
            row.finished_at = finished
            row.doc = doc
            return self._serialize(row)

    async def mark_cancelled(self, job_id: str, *, reason: str | None = None) -> dict[str, Any] | None:
        """Terminal cancel for an open startup job. Idempotent if already terminal."""
        async with session_scope() as session:
            row = await session.get(AiStrategyStartupJobRow, job_id)
            if row is None:
                return None
            if row.status not in STARTUP_OPEN_STATUSES:
                return self._serialize(row)
            finished = _now()
            doc = dict(row.doc)
            doc["status"] = STARTUP_STATUS_CANCELLED
            doc["finished_at"] = finished.isoformat()
            doc["pending_reports"] = []
            if reason:
                doc["error"] = (reason or "")[:2000]
            else:
                doc["error"] = None
            row.status = STARTUP_STATUS_CANCELLED
            row.finished_at = finished
            row.doc = doc
            return self._serialize(row)

    @staticmethod
    def _serialize(row: AiStrategyStartupJobRow) -> dict[str, Any]:
        doc = dict(row.doc)
        return {
            **doc,
            "id": row.id,
            "strategy_id": row.strategy_id,
            "status": row.status,
            "phase": row.phase,
            "created_at": row.created_at.isoformat(),
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }
