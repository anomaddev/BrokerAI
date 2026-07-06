from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from brokerai.db.repositories.cost_ledger import CostLedgerRepository

logger = logging.getLogger(__name__)


async def record_cost_entry(
    category: str,
    amount_usd: float | None,
    description: str,
    *,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Append a cost ledger row; failures are logged and never raised."""
    try:
        return await CostLedgerRepository().append(
            category,
            amount_usd,
            description,
            source=source,
            metadata=metadata,
            occurred_at=occurred_at,
        )
    except Exception:
        logger.warning(
            "Failed to record cost entry: category=%s description=%s",
            category,
            description,
            exc_info=True,
        )
        return None


def record_cost_entry_task(
    category: str,
    amount_usd: float | None,
    description: str,
    *,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """Fire-and-forget helper for call sites with a running event loop."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    loop.create_task(
        record_cost_entry(
            category,
            amount_usd,
            description,
            source=source,
            metadata=metadata,
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )
    )
