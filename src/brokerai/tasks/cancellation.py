from __future__ import annotations

import asyncio

from brokerai.tasks.state import TaskRunnerState


class TaskCancelled(Exception):
    """Raised when a background task receives a cooperative cancel request."""


class CancellationToken:
    """Cooperative cancellation token shared across processes via persisted state."""

    def __init__(self, task_id: str, state: TaskRunnerState) -> None:
        self.task_id = task_id
        self._state = state
        self._event = asyncio.Event()

    def request_cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        if self._event.is_set():
            return True
        active = self._state.read_active_unlocked()
        if not active or active.get("id") != self.task_id:
            return False
        return active.get("cancel_requested_at") is not None

    def check(self) -> None:
        if self.is_cancelled():
            raise TaskCancelled(f"Task {self.task_id} cancelled")
