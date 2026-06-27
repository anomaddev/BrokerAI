from __future__ import annotations

from pathlib import Path

import pytest

from brokerai.db.repositories.research_settings import _normalize_settings
from brokerai.tasks.cancellation import CancellationToken, TaskCancelled
from brokerai.tasks.state import TaskRunnerState


def test_normalize_settings_migrates_legacy_model_id():
    doc = {
        "selected_model_id": "model-a",
        "reasoning_effort": "medium",
    }
    normalized = _normalize_settings(doc)
    assert normalized["contributor_models"] == [
        {"model_id": "model-a", "reasoning_effort": "medium", "enabled": True}
    ]


def test_cancellation_token_raises_when_flag_set(tmp_path: Path):
    from brokerai.config.settings import Settings

    settings = Settings(data_dir=tmp_path)
    state = TaskRunnerState(settings)
    state.persist_active(
        {
            "id": "task-1",
            "kind": "research_daily",
            "status": "running",
            "cancel_requested_at": "2026-01-01T00:00:00+00:00",
        }
    )
    token = CancellationToken("task-1", state)
    with pytest.raises(TaskCancelled):
        token.check()


def test_reconcile_stale_cancelled_task(tmp_path: Path, monkeypatch):
    from brokerai.config.settings import Settings
    import brokerai.tasks.runner as runner_module

    settings = Settings(data_dir=tmp_path)
    monkeypatch.setattr(runner_module, "get_settings", lambda: settings)
    runner_module._state = TaskRunnerState(settings)

    state = TaskRunnerState(settings)
    state.persist_active(
        {
            "id": "task-stale",
            "kind": "research_daily",
            "label": "Daily research report",
            "status": "running",
            "message": "Cancelling…",
            "cancel_requested_at": "2026-01-01T00:00:00+00:00",
        }
    )

    runner_module.reconcile_stale_active_task()
    assert runner_module.get_active_task() is None

    recent = state.read_state().get("recent") or []
    assert recent[-1]["status"] == "cancelled"


def test_task_runner_state_file_lock_serializes_writes(tmp_path: Path):
    from brokerai.config.settings import Settings

    settings = Settings(data_dir=tmp_path)
    state = TaskRunnerState(settings)
    results: list[str | None] = []

    def writer(task_id: str) -> None:
        with state.file_lock():
            active = state.read_active_unlocked()
            if active is None:
                state._write_state_unlocked(
                    {
                        "active": {"id": task_id, "status": "running"},
                        "recent": [],
                    }
                )
                results.append(task_id)
            else:
                results.append(None)

    writer("a")
    writer("b")
    assert results == ["a", None]
