from __future__ import annotations

from datetime import datetime
from typing import Any

from brokerai.integrations.oanda import parse_oanda_close_response


def close_details_from_metadata(close_metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Extract normalized close fields stored under ``close_metadata.broker_close``."""
    if not close_metadata:
        return {}
    broker_close = close_metadata.get("broker_close")
    if isinstance(broker_close, dict):
        return parse_oanda_close_response(broker_close)
    return {}


def resolved_close_fields(doc: dict[str, Any]) -> dict[str, Any]:
    """Merge persisted close fields with values recoverable from metadata."""
    exit_price = doc.get("exit_price")
    realized_pl = doc.get("realized_pl")
    closed_at = doc.get("closed_at")

    if doc.get("status") != "closed":
        return {
            "exit_price": exit_price,
            "realized_pl": realized_pl,
            "closed_at": closed_at,
        }

    from_metadata = close_details_from_metadata(doc.get("close_metadata"))
    if exit_price is None:
        exit_price = from_metadata.get("exit_price")
    if realized_pl is None:
        realized_pl = from_metadata.get("realized_pl")
    if closed_at is None:
        closed_at = from_metadata.get("closed_at")

    return {
        "exit_price": exit_price,
        "realized_pl": realized_pl,
        "closed_at": closed_at,
    }


def close_details_need_backfill(doc: dict[str, Any]) -> bool:
    """Return True when a closed trade is missing exit price or realized P/L."""
    if doc.get("status") != "closed":
        return False
    fields = resolved_close_fields(doc)
    return fields.get("exit_price") is None or fields.get("realized_pl") is None
