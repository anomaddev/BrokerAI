from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, TypeVar

from brokerai.bots.base import EphemeralBot, WorkerResult
from brokerai.bots.secretary.types import WorkerHandle, WorkerState

logger = logging.getLogger(__name__)

RequestT = TypeVar("RequestT")
ResultT = TypeVar("ResultT")


class WorkerPool:
    """In-process spin-up/spin-down pool for ephemeral pipeline workers."""

    def __init__(self) -> None:
        self._active: dict[str, WorkerHandle] = {}
        self._completed_count = 0

    @property
    def active_count(self) -> int:
        return sum(1 for h in self._active.values() if h.state == WorkerState.RUNNING)

    @property
    def active_handles(self) -> list[WorkerHandle]:
        return list(self._active.values())

    def status(self) -> dict[str, Any]:
        return {
            "active_workers": self.active_count,
            "total_handles": len(self._active),
            "completed_total": self._completed_count,
            "handles": [
                {
                    "handle_id": h.handle_id,
                    "worker_name": h.worker_name,
                    "asset_class": h.asset_class,
                    "state": h.state.value,
                    "job_id": h.job_id,
                    "started_at": h.started_at.isoformat(),
                }
                for h in self._active.values()
            ],
        }

    async def run(
        self,
        worker_cls: type[EphemeralBot[Any, ResultT]],
        request: RequestT,
        *,
        job_id: str | None = None,
    ) -> WorkerResult[ResultT]:
        handle_id = str(uuid.uuid4())
        worker = worker_cls()
        name = getattr(worker_cls, "name", worker_cls.__name__)
        asset_class = getattr(worker, "asset_class", "unknown")
        handle = WorkerHandle(
            handle_id=handle_id,
            worker_name=name,
            asset_class=str(asset_class),
            state=WorkerState.RUNNING,
            started_at=datetime.now(timezone.utc),
            job_id=job_id,
        )
        self._active[handle_id] = handle
        try:
            await worker.start()
            result = await worker.run(request)
            handle.state = WorkerState.COMPLETED if result.ok else WorkerState.FAILED
            self._completed_count += 1
            return result
        except Exception as exc:
            logger.exception("Worker %s failed", name)
            handle.state = WorkerState.FAILED
            self._completed_count += 1
            return WorkerResult(ok=False, error=str(exc))
        finally:
            try:
                await worker.stop()
            except Exception:
                logger.warning("Worker %s stop failed", name, exc_info=True)
            self._active.pop(handle_id, None)


_GLOBAL_POOL: WorkerPool | None = None


def get_worker_pool() -> WorkerPool:
    global _GLOBAL_POOL
    if _GLOBAL_POOL is None:
        _GLOBAL_POOL = WorkerPool()
    return _GLOBAL_POOL
