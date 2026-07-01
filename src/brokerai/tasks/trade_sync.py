"""Background task adapter for manual OANDA trade sync."""

from __future__ import annotations

import httpx

from brokerai.tasks.cancellation import CancellationToken
from brokerai.tasks.kinds import task_kind_spec
from brokerai.tasks.runner import (
    finish_task_failed,
    finish_task_skipped,
    finish_task_success,
    start_task,
    update_task,
)
from brokerai.trading.trade_sync import sync_oanda_trades_to_ledger


def _sync_success_message(result: dict) -> str:
    imported = int(result.get("imported", 0))
    updated = int(result.get("updated", 0))
    closed = int(result.get("closed", 0))
    backfilled = int(result.get("backfilled", 0))
    if imported == 0 and updated == 0 and closed == 0 and backfilled == 0:
        return "Ledger and OANDA are already in sync"
    parts: list[str] = []
    if imported:
        parts.append(f"{imported} imported")
    if updated:
        parts.append(f"{updated} updated")
    if closed:
        parts.append(f"{closed} closed")
    if backfilled:
        parts.append(f"{backfilled} backfilled")
    return f"Sync complete — {', '.join(parts)}"


async def start_trade_sync_task(*, label: str = "Sync OANDA trades") -> tuple[str | None, str | None]:
    spec = task_kind_spec("trade_sync")
    if spec is None:
        return None, "trade_sync kind is not registered"

    async def work(token: CancellationToken) -> None:
        token.check()
        update_task("fetch", "Fetching OANDA open trades…", 25)
        result = await sync_oanda_trades_to_ledger()
        token.check()

        if not result.get("configured"):
            reason = "Connect OANDA in Settings → Exchange Connections"
            await finish_task_skipped(
                reason,
                result={**result, "skipped_reason": reason},
            )
            return

        if result.get("error"):
            await finish_task_failed(str(result["error"]))
            return

        update_task("reconcile", "Reconciling ledger…", 75)
        token.check()
        await finish_task_success(result, message=_sync_success_message(result))

    return await start_task("trade_sync", label, work)
