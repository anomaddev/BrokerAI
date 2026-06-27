"""Stub adapter for future executor/trade background jobs."""

from __future__ import annotations

from brokerai.tasks.cancellation import CancellationToken
from brokerai.tasks.kinds import task_kind_spec
from brokerai.tasks.runner import finish_task_failed, start_task, update_task


async def start_trade_execute_task(*, label: str = "Execute trade") -> tuple[str | None, str | None]:
    spec = task_kind_spec("trade_execute")
    if spec is None:
        return None, "trade_execute kind is not registered"

    async def work(_token: CancellationToken) -> None:
        update_task("start", "Trade execution is not implemented yet", 0)
        await finish_task_failed("Executor bot is not implemented")

    return await start_task("trade_execute", label, work)
