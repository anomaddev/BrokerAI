"""Optional unread research-reports email digest (no-op without outbound mail)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def send_unread_reports_digest(*, user_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Send an unread-reports digest if mail + flag are configured.

    BrokerAI has no outbound mail transport today. This helper is the extension
    point: when ``unread_digest_enabled`` is true it logs a skip reason unless a
    future mail backend is wired.
    """
    if not settings.get("unread_digest_enabled"):
        return {"ok": False, "skipped_reason": "Unread digest is disabled"}

    # Future: integrate SMTP / provider here.
    logger.info(
        "Unread research digest skipped for user=%s (no outbound mail transport)",
        user_id,
    )
    return {
        "ok": False,
        "skipped_reason": "Outbound mail is not configured",
    }
