"""Repositories for AI Strategy memory digests and batched learning jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import LearningJobRow, StrategyMemoryDigestRow

LEARNING_JOB_STATUS_QUEUED = "queued"
LEARNING_JOB_STATUS_RUNNING = "running"
LEARNING_JOB_STATUS_COMPLETED = "completed"
LEARNING_JOB_STATUS_FAILED = "failed"

LEARNING_JOB_OPEN_STATUSES = frozenset(
    {LEARNING_JOB_STATUS_QUEUED, LEARNING_JOB_STATUS_RUNNING}
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_dt(raw: Any) -> datetime | None:
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


class StrategyMemoryDigestsRepository:
    """Versioned JSONB digests keyed by strategy_id."""

    async def get_latest(self, strategy_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(StrategyMemoryDigestRow)
                    .where(StrategyMemoryDigestRow.strategy_id == strategy_id)
                    .order_by(StrategyMemoryDigestRow.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "id": row.id,
                "strategy_id": row.strategy_id,
                "version": row.version,
                "created_at": row.created_at.isoformat(),
                **dict(row.doc),
                "version": row.version,
            }

    async def get_for_strategy(self, strategy_id: str) -> dict[str, Any] | None:
        """Alias used by daily compiled-playbook backtests (Slice 4)."""
        return await self.get_latest(strategy_id)

    async def next_version(self, strategy_id: str) -> int:
        async with session_scope() as session:
            current = (
                await session.execute(
                    select(func.max(StrategyMemoryDigestRow.version)).where(
                        StrategyMemoryDigestRow.strategy_id == strategy_id
                    )
                )
            ).scalar_one()
            return int(current or 0) + 1

    async def create_version(
        self,
        strategy_id: str,
        doc: dict[str, Any],
        *,
        version: int | None = None,
    ) -> dict[str, Any]:
        """Insert a new digest version. Idempotent only via unique (strategy_id, version)."""
        digest_id = str(doc.get("id") or uuid4().hex)
        ver = int(version) if version is not None else await self.next_version(strategy_id)
        created = _now()
        payload = {
            **doc,
            "id": digest_id,
            "strategy_id": strategy_id,
            "version": ver,
            "created_at": created.isoformat(),
        }
        async with session_scope() as session:
            session.add(
                StrategyMemoryDigestRow(
                    id=digest_id,
                    strategy_id=strategy_id,
                    version=ver,
                    created_at=created,
                    doc=payload,
                )
            )
        return payload

    async def covered_through(self, strategy_id: str) -> datetime | None:
        """Return the latest outcome exit_ts covered by the current digest, if any."""
        latest = await self.get_latest(strategy_id)
        if not latest:
            return None
        return _parse_iso_dt(latest.get("covered_through"))


class LearningJobsRepository:
    """Queued/running/completed batched learning jobs."""

    async def enqueue(self, strategy_id: str, doc: dict[str, Any] | None = None) -> dict[str, Any]:
        job_id = str((doc or {}).get("id") or uuid4().hex)
        created = _now()
        payload = {
            **(doc or {}),
            "id": job_id,
            "strategy_id": strategy_id,
            "status": LEARNING_JOB_STATUS_QUEUED,
            "created_at": created.isoformat(),
        }
        async with session_scope() as session:
            session.add(
                LearningJobRow(
                    id=job_id,
                    strategy_id=strategy_id,
                    status=LEARNING_JOB_STATUS_QUEUED,
                    created_at=created,
                    started_at=None,
                    finished_at=None,
                    doc=payload,
                )
            )
        return payload

    async def get_by_id(self, job_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(LearningJobRow, job_id)
            if row is None:
                return None
            return self._serialize(row)

    async def has_open_job(self, strategy_id: str) -> bool:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(LearningJobRow.id)
                    .where(
                        LearningJobRow.strategy_id == strategy_id,
                        LearningJobRow.status.in_(tuple(LEARNING_JOB_OPEN_STATUSES)),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            return row is not None

    async def list_queued(self, *, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(LearningJobRow)
                    .where(LearningJobRow.status == LEARNING_JOB_STATUS_QUEUED)
                    .order_by(LearningJobRow.created_at.asc())
                    .limit(limit)
                )
            ).scalars().all()
            return [self._serialize(row) for row in rows]

    async def mark_running(self, job_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(LearningJobRow, job_id)
            if row is None:
                return None
            if row.status not in {
                LEARNING_JOB_STATUS_QUEUED,
                LEARNING_JOB_STATUS_RUNNING,
            }:
                return self._serialize(row)
            started = _now()
            doc = dict(row.doc)
            doc["status"] = LEARNING_JOB_STATUS_RUNNING
            doc["started_at"] = started.isoformat()
            row.status = LEARNING_JOB_STATUS_RUNNING
            row.started_at = started
            row.doc = doc
            return self._serialize(row)

    async def mark_completed(
        self,
        job_id: str,
        *,
        digest_id: str | None = None,
        digest_version: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(LearningJobRow, job_id)
            if row is None:
                return None
            finished = _now()
            doc = dict(row.doc)
            doc["status"] = LEARNING_JOB_STATUS_COMPLETED
            doc["finished_at"] = finished.isoformat()
            if digest_id is not None:
                doc["digest_id"] = digest_id
            if digest_version is not None:
                doc["digest_version"] = digest_version
            if extra:
                doc.update(extra)
            row.status = LEARNING_JOB_STATUS_COMPLETED
            row.finished_at = finished
            row.doc = doc
            return self._serialize(row)

    async def mark_failed(self, job_id: str, *, error: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(LearningJobRow, job_id)
            if row is None:
                return None
            finished = _now()
            doc = dict(row.doc)
            doc["status"] = LEARNING_JOB_STATUS_FAILED
            doc["finished_at"] = finished.isoformat()
            doc["error"] = (error or "unknown")[:2000]
            row.status = LEARNING_JOB_STATUS_FAILED
            row.finished_at = finished
            row.doc = doc
            return self._serialize(row)

    @staticmethod
    def _serialize(row: LearningJobRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "strategy_id": row.strategy_id,
            "status": row.status,
            "created_at": row.created_at.isoformat(),
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            **dict(row.doc),
            "status": row.status,
        }
