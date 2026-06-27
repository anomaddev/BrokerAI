"""Background task runner with cross-process file locking and cooperative cancellation."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from brokerai.config.settings import get_settings
from brokerai.tasks.cancellation import CancellationToken, TaskCancelled
from brokerai.tasks.kinds import RESEARCH_KINDS, task_kind_spec
from brokerai.tasks.state import TaskRunnerState
from brokerai.util.time import utc_now_iso

logger = logging.getLogger(__name__)

TaskStatus = str  # re-exported via kinds for callers

ProgressCallback = Callable[[str, str, int], None]

_MAX_RECENT = 10
_STALE_RUNNING_SECONDS = 3600
_local_task: asyncio.Task[None] | None = None
_lock = asyncio.Lock()
_tokens: dict[str, CancellationToken] = {}
_state: TaskRunnerState | None = None


def _get_state() -> TaskRunnerState:
    global _state
    if _state is None:
        _state = TaskRunnerState()
    return _state


def _active_running_task() -> dict[str, Any] | None:
    active = _get_state().read_state().get("active")
    if not isinstance(active, dict):
        return None
    if active.get("status") != "running":
        return None
    return active


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _worker_still_running(active: dict[str, Any]) -> bool:
    pid_raw = active.get("worker_pid")
    if pid_raw is None:
        return False
    try:
        pid = int(pid_raw)
    except (TypeError, ValueError):
        return False

    if pid != os.getpid():
        return _is_pid_alive(pid)

    global _local_task
    return _local_task is not None and not _local_task.done()


def _should_reconcile_stale_active(active: dict[str, Any]) -> bool:
    if active.get("status") != "running":
        return False
    if _worker_still_running(active):
        return False
    if active.get("cancel_requested_at"):
        return True
    if not active.get("started_at"):
        return True
    started = _parse_iso(active.get("started_at"))
    if started is None:
        return True
    age = (datetime.now(timezone.utc) - started.astimezone(timezone.utc)).total_seconds()
    return age > _STALE_RUNNING_SECONDS


def _finalize_stale_active(active: dict[str, Any]) -> None:
    state_obj = _get_state()
    with state_obj.file_lock():
        state = state_obj._read_state_unlocked()
        current = state.get("active")
        if not isinstance(current, dict) or current.get("id") != active.get("id"):
            return
        if current.get("status") != "running":
            return
        if not _should_reconcile_stale_active(current):
            return

        if current.get("cancel_requested_at"):
            current["status"] = "cancelled"
            current["message"] = "Cancelled"
        else:
            current["status"] = "failed"
            current["message"] = "Task interrupted (process stopped)"
            current["error"] = current["message"]
        current["finished_at"] = utc_now_iso()
        recent = state.get("recent") or []
        recent.append(current)
        state["recent"] = recent[-_MAX_RECENT:]
        state["active"] = None
        state_obj._write_state_unlocked(state)
        logger.info(
            "Reconciled stale background task %s (%s) as %s",
            current.get("id"),
            current.get("kind"),
            current.get("status"),
        )
    _clear_token(active.get("id"))


def reconcile_stale_active_task() -> None:
    """Clear orphaned active tasks left after a crash or restart."""
    active = _active_running_task()
    if active is not None and _should_reconcile_stale_active(active):
        _finalize_stale_active(active)


def update_task(step: str, message: str, progress: int) -> None:
    state_obj = _get_state()
    with state_obj.file_lock():
        state = state_obj._read_state_unlocked()
        active = state.get("active")
        if not active or active.get("status") != "running":
            return
        active["step"] = step
        active["message"] = message
        active["progress"] = max(0, min(100, progress))
        state_obj._write_state_unlocked(state)

    task_id = active.get("id") if isinstance(active, dict) else None
    if isinstance(task_id, str):
        token = _tokens.get(task_id)
        if token is not None:
            token.check()


def make_progress_callback() -> ProgressCallback:
    return update_task


def is_research_running() -> bool:
    active = get_active_task()
    return active is not None and active.get("kind") in RESEARCH_KINDS


def get_active_task() -> dict[str, Any] | None:
    reconcile_stale_active_task()
    return _active_running_task()


def get_recent_tasks(limit: int = 3) -> list[dict[str, Any]]:
    recent = _get_state().read_state().get("recent") or []
    if not isinstance(recent, list):
        return []
    items = [item for item in recent if isinstance(item, dict)][-limit:]
    items.reverse()
    return items


async def finish_task_success(
    result: dict[str, Any] | None = None,
    *,
    message: str = "Complete",
) -> None:
    state_obj = _get_state()
    with state_obj.file_lock():
        state = state_obj._read_state_unlocked()
        active = state.get("active")
        if not isinstance(active, dict) or active.get("status") != "running":
            return
        active["status"] = "success"
        active["message"] = message
        active["progress"] = 100
        active["step"] = "done"
        active["finished_at"] = utc_now_iso()
        active["result"] = result
        recent = state.get("recent") or []
        recent.append(active)
        state["recent"] = recent[-_MAX_RECENT:]
        state["active"] = None
        state_obj._write_state_unlocked(state)
    _clear_token(active.get("id"))


async def finish_task_failed(error: str, *, message: str | None = None) -> None:
    state_obj = _get_state()
    with state_obj.file_lock():
        state = state_obj._read_state_unlocked()
        active = state.get("active")
        if not isinstance(active, dict) or active.get("status") != "running":
            return
        active["status"] = "failed"
        active["error"] = error
        active["message"] = message or error
        active["finished_at"] = utc_now_iso()
        recent = state.get("recent") or []
        recent.append(active)
        state["recent"] = recent[-_MAX_RECENT:]
        state["active"] = None
        state_obj._write_state_unlocked(state)
    _clear_token(active.get("id"))


async def finish_task_skipped(
    reason: str,
    *,
    result: dict[str, Any] | None = None,
) -> None:
    state_obj = _get_state()
    with state_obj.file_lock():
        state = state_obj._read_state_unlocked()
        active = state.get("active")
        if not isinstance(active, dict) or active.get("status") != "running":
            return
        active["status"] = "skipped"
        active["message"] = reason
        active["finished_at"] = utc_now_iso()
        active["result"] = result
        recent = state.get("recent") or []
        recent.append(active)
        state["recent"] = recent[-_MAX_RECENT:]
        state["active"] = None
        state_obj._write_state_unlocked(state)
    _clear_token(active.get("id"))


async def finish_task_cancelled(*, message: str = "Cancelled") -> None:
    state_obj = _get_state()
    with state_obj.file_lock():
        state = state_obj._read_state_unlocked()
        active = state.get("active")
        if not isinstance(active, dict) or active.get("status") != "running":
            return
        active["status"] = "cancelled"
        active["message"] = message
        active["finished_at"] = utc_now_iso()
        recent = state.get("recent") or []
        recent.append(active)
        state["recent"] = recent[-_MAX_RECENT:]
        state["active"] = None
        state_obj._write_state_unlocked(state)
    _clear_token(active.get("id"))


def _clear_token(task_id: Any) -> None:
    if isinstance(task_id, str):
        _tokens.pop(task_id, None)


def _token_for(task_id: str) -> CancellationToken:
    token = _tokens.get(task_id)
    if token is None:
        token = CancellationToken(task_id, _get_state())
        _tokens[task_id] = token
    return token


async def cancel_task(task_id: str) -> tuple[bool, str | None]:
    """Request cancellation. Returns (ok, error_message)."""
    state_obj = _get_state()
    with state_obj.file_lock():
        state = state_obj._read_state_unlocked()
        active = state.get("active")
        if not isinstance(active, dict) or active.get("id") != task_id:
            return False, "Task not found or not active"
        if active.get("status") != "running":
            return False, "Task is not running"

        spec = task_kind_spec(str(active.get("kind") or ""))
        if spec is None or not spec.cancellable:
            return False, "Task kind cannot be cancelled"

        if active.get("cancel_requested_at"):
            return True, None

        active["cancel_requested_at"] = utc_now_iso()
        active["message"] = "Cancelling…"
        state_obj._write_state_unlocked(state)

    token = _token_for(task_id)
    token.request_cancel()

    global _local_task
    if _local_task is not None and not _local_task.done():
        local_active = get_active_task()
        if local_active and local_active.get("id") == task_id:
            _local_task.cancel()

    return True, None


async def start_task(
    kind: str,
    label: str,
    work: Callable[[CancellationToken], Awaitable[None]],
    *,
    exclusive_kinds: frozenset[str] | None = None,
    cancellable: bool | None = None,
) -> tuple[str | None, str | None]:
    """Start a background task. Returns (task_id, error_message)."""
    global _local_task

    spec = task_kind_spec(kind)
    if exclusive_kinds is None and spec is not None:
        exclusive_kinds = spec.exclusive_kinds
    if cancellable is None:
        cancellable = spec.cancellable if spec is not None else False

    state_obj = _get_state()

    async with _lock:
        with state_obj.file_lock():
            active = state_obj.read_active_unlocked()
            if active is not None:
                conflict = exclusive_kinds is None or active.get("kind") in exclusive_kinds
                if conflict:
                    return None, f"A task is already running: {active.get('label', 'task')}"

            task_id = str(uuid.uuid4())
            task = {
                "id": task_id,
                "kind": kind,
                "label": label,
                "status": "running",
                "message": "Starting…",
                "step": "start",
                "progress": 0,
                "started_at": utc_now_iso(),
                "finished_at": None,
                "result": None,
                "error": None,
                "cancellable": cancellable,
                "cancel_requested_at": None,
                "worker_pid": os.getpid(),
            }
            state = state_obj._read_state_unlocked()
            state["active"] = task
            state_obj._write_state_unlocked(state)

    token = _token_for(task_id)

    async def runner() -> None:
        try:
            await work(token)
        except TaskCancelled:
            await finish_task_cancelled()
        except asyncio.CancelledError:
            await finish_task_cancelled()
            raise
        except Exception as exc:
            logger.exception("Background task %s failed", kind)
            await finish_task_failed(str(exc))

    asyncio_task = asyncio.create_task(runner())
    _local_task = asyncio_task

    def _done(async_task: asyncio.Task[None]) -> None:
        global _local_task
        if _local_task is async_task:
            _local_task = None
        if async_task.cancelled():
            return
        exc = async_task.exception()
        if exc and not isinstance(exc, asyncio.CancelledError):
            active_now = get_active_task()
            if active_now and active_now.get("id") == task_id:
                logger.error("Background task %s exited without finalizing: %s", kind, exc)

    asyncio_task.add_done_callback(_done)
    return task_id, None
