from __future__ import annotations

_KEY_SEP = ":"


def broker_lot_key(exchange_id: str, broker_lot_id: str) -> str:
    """Cross-broker surrogate key for logs and dashboards (not stored in MongoDB)."""
    return f"{exchange_id}{_KEY_SEP}{broker_lot_id}"


def broker_event_key(exchange_id: str, broker_event_id: str) -> str:
    """Cross-broker surrogate key for an audit event."""
    return f"{exchange_id}{_KEY_SEP}{broker_event_id}"


def parse_broker_lot_key(key: str) -> tuple[str, str]:
    """Split a ``broker_lot_key`` into ``(exchange_id, broker_lot_id)``."""
    exchange_id, _, broker_lot_id = key.partition(_KEY_SEP)
    if not broker_lot_id:
        raise ValueError(f"invalid broker lot key: {key!r}")
    return exchange_id, broker_lot_id


def parse_broker_event_key(key: str) -> tuple[str, str]:
    """Split a ``broker_event_key`` into ``(exchange_id, broker_event_id)``."""
    exchange_id, _, broker_event_id = key.partition(_KEY_SEP)
    if not broker_event_id:
        raise ValueError(f"invalid broker event key: {key!r}")
    return exchange_id, broker_event_id
