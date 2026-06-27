from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from brokerai.db.repositories.bot_activity import BotActivityRepository

logger = logging.getLogger(__name__)


async def record_bot_activity(
    action_type: str,
    title: str,
    *,
    detail: str | None = None,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any] | None:
    try:
        return await BotActivityRepository().append(
            action_type=action_type,
            title=title,
            detail=detail,
            source=source,
            metadata=metadata,
            occurred_at=occurred_at,
        )
    except Exception:
        logger.warning("Failed to record bot activity: %s — %s", action_type, title, exc_info=True)
        return None


def record_bot_activity_sync(
    action_type: str,
    title: str,
    *,
    detail: str | None = None,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """Fire-and-forget helper for call sites without a running loop context."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    loop.create_task(
        record_bot_activity(
            action_type,
            title,
            detail=detail,
            source=source,
            metadata=metadata,
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )
    )
