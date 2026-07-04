from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from brokerai.config.settings import get_settings
from brokerai.trading.broker.models import BrokerEvent

logger = logging.getLogger(__name__)

TRADE_LINKED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "ORDER_FILL",
        "ORDER_CANCEL",
        "ORDER_CANCEL_REJECT",
        "ORDER_REJECT",
        "STOP_LOSS_ORDER",
        "STOP_LOSS",
        "TAKE_PROFIT_ORDER",
        "TAKE_PROFIT",
        "TRADE_CLOSE",
        "TRADE_CLOSED",
        "TRADE_OPENED",
        "TRADE_REDUCE",
        "MARKET_ORDER",
        "LIMIT_ORDER",
        "STOP_ORDER",
        "MARKET_ORDER_REJECT",
        "LIMIT_ORDER_REJECT",
        "STOP_ORDER_REJECT",
    }
)

LOW_VALUE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "MARGIN_CALL",
        "MARGIN_CALL_ENTER",
        "MARGIN_CALL_EXIT",
        "DAILY_FINANCING",
        "TRANSFER_FUNDS",
        "DEPOSIT",
        "WITHDRAWAL",
        "ACCOUNT_ALIAS",
        "CLIENT_CONFIGURE",
        "CLIENT_CONFIGURE_REJECT",
    }
)


def collect_protected_event_ids(lot_docs: list[dict[str, Any]]) -> frozenset[str]:
    """Event IDs that must never receive a TTL (open lots + incomplete closes)."""
    protected: set[str] = set()
    for lot in lot_docs:
        state = str(lot.get("state") or "")
        if state == "open":
            last_event = lot.get("last_event_id")
            if last_event:
                protected.add(str(last_event))
            for event_id in lot.get("closing_event_ids") or []:
                protected.add(str(event_id))
            for child_key in ("stop_loss", "take_profit"):
                child = lot.get(child_key)
                if not isinstance(child, dict):
                    continue
                for field in ("filling_event_id", "cancelling_event_id"):
                    value = child.get(field)
                    if value:
                        protected.add(str(value))
        elif state == "closed":
            missing_exit = lot.get("exit_price") is None or lot.get("realized_pl") is None
            if missing_exit:
                for event_id in lot.get("closing_event_ids") or []:
                    protected.add(str(event_id))
                last_event = lot.get("last_event_id")
                if last_event:
                    protected.add(str(last_event))
    return frozenset(protected)


def classify_event_retention(
    event: BrokerEvent,
    *,
    protected_event_ids: frozenset[str] | None = None,
    retention_days: int | None = None,
    enabled: bool | None = None,
) -> datetime | None:
    """Return ``retention_expires_at`` for low-value events, or ``None`` to keep forever."""
    settings = get_settings()
    if enabled is None:
        enabled = settings.broker_events_retention_enabled
    if not enabled:
        return None

    if protected_event_ids and event.broker_event_id in protected_event_ids:
        return None

    if event.broker_lot_id or event.broker_order_id:
        return None

    event_type = event.event_type.upper()
    if event_type in TRADE_LINKED_EVENT_TYPES:
        return None

    if event_type not in LOW_VALUE_EVENT_TYPES:
        return None

    days = retention_days if retention_days is not None else settings.broker_events_low_value_retention_days
    base_time = event.time
    if base_time is None:
        base_time = datetime.now(timezone.utc)
    elif base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=timezone.utc)
    else:
        base_time = base_time.astimezone(timezone.utc)

    return base_time + timedelta(days=max(1, days))


def log_retention_dry_run(
    events: list[BrokerEvent],
    protected_event_ids: frozenset[str],
) -> int:
    """Count events that would be TTL'd but are protected; log at WARNING if any."""
    would_expire_but_protected = 0
    for event in events:
        if event.broker_event_id not in protected_event_ids:
            continue
        tentative = classify_event_retention(
            event,
            protected_event_ids=None,
            enabled=True,
        )
        if tentative is not None:
            would_expire_but_protected += 1
    if would_expire_but_protected:
        logger.warning(
            "Event retention dry-run: %d protected events would have received TTL",
            would_expire_but_protected,
        )
    return would_expire_but_protected
