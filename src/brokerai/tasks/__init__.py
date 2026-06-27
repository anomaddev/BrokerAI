"""Shared background task runner for web and orchestrator processes."""

from brokerai.tasks.cancellation import CancellationToken, TaskCancelled
from brokerai.tasks.kinds import RESEARCH_KINDS, TASK_KINDS, TaskKindSpec
from brokerai.tasks.runner import (
    cancel_task,
    finish_task_cancelled,
    finish_task_failed,
    finish_task_skipped,
    finish_task_success,
    get_active_task,
    get_recent_tasks,
    is_research_running,
    make_progress_callback,
    reconcile_stale_active_task,
    start_task,
    update_task,
)

__all__ = [
    "CancellationToken",
    "RESEARCH_KINDS",
    "TASK_KINDS",
    "TaskCancelled",
    "TaskKindSpec",
    "cancel_task",
    "finish_task_cancelled",
    "finish_task_failed",
    "finish_task_skipped",
    "finish_task_success",
    "get_active_task",
    "get_recent_tasks",
    "is_research_running",
    "make_progress_callback",
    "reconcile_stale_active_task",
    "start_task",
    "update_task",
]
