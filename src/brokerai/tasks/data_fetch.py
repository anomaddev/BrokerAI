"""Stub adapter for future data_manager background jobs."""

from __future__ import annotations

from brokerai.tasks.cancellation import CancellationToken
from brokerai.tasks.kinds import task_kind_spec
from brokerai.tasks.runner import finish_task_failed, start_task, update_task


async def start_data_fetch_task(*, label: str = "Fetch market data") -> tuple[str | None, str | None]:
    spec = task_kind_spec("data_fetch")
    if spec is None:
        return None, "data_fetch kind is not registered"

    async def work(_token: CancellationToken) -> None:
        update_task("start", "Data fetch is not implemented yet", 0)
        await finish_task_failed("Data manager bot is not implemented")

    return await start_task("data_fetch", label, work)
