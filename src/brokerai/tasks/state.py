from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from brokerai.config.settings import Settings, get_settings

_MAX_RECENT = 10


class TaskRunnerState:
    """On-disk task state with cross-process file locking."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

    def state_path(self) -> Path:
        return self.settings.data_dir / "background-task-state.json"

    def lock_path(self) -> Path:
        return self.settings.data_dir / "background-task-state.lock"

    @contextmanager
    def file_lock(self):
        lock_path = self.lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def default_state() -> dict[str, Any]:
        return {"active": None, "recent": []}

    def read_state(self) -> dict[str, Any]:
        with self.file_lock():
            return self._read_state_unlocked()

    def read_active_unlocked(self) -> dict[str, Any] | None:
        state = self._read_state_unlocked()
        active = state.get("active")
        return active if isinstance(active, dict) else None

    def _read_state_unlocked(self) -> dict[str, Any]:
        path = self.state_path()
        if not path.exists():
            return self.default_state()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    "active": data.get("active"),
                    "recent": data.get("recent") if isinstance(data.get("recent"), list) else [],
                }
        except (OSError, json.JSONDecodeError):
            pass
        return self.default_state()

    def _write_state_unlocked(self, state: dict[str, Any]) -> None:
        path = self.state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def persist_active(self, active: dict[str, Any] | None) -> None:
        with self.file_lock():
            state = self._read_state_unlocked()
            state["active"] = active
            self._write_state_unlocked(state)

    def append_recent(self, task: dict[str, Any]) -> None:
        with self.file_lock():
            state = self._read_state_unlocked()
            recent = state.get("recent") or []
            recent.append(task)
            state["recent"] = recent[-_MAX_RECENT:]
            state["active"] = None
            self._write_state_unlocked(state)
