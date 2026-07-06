from __future__ import annotations

from datetime import datetime
from typing import Any

from brokerai.market_sessions import (
    TRADING_SESSIONS,
    is_forex_hours,
    is_session_active,
    normalize_enabled_sessions,
)

SESSION_ALIASES: dict[str, str] = {
    "London": "london",
    "NY": "ny",
    "Asia": "asia",
    "Sydney": "sydney",
    "Tokyo": "asia",
    "Singapore": "asia",
    "Hong Kong": "asia",
    "China": "asia",
    "london": "london",
    "ny": "ny",
    "asia": "asia",
    "sydney": "sydney",
    "tokyo": "asia",
    "singapore": "asia",
    "hong_kong": "asia",
    "china": "asia",
}

_SESSION_BY_ID = {session.id: session for session in TRADING_SESSIONS}


def normalize_strategy_session(name: str) -> str | None:
    return SESSION_ALIASES.get(name)


def normalize_strategy_sessions(sessions: list[str]) -> list[str]:
    normalized: list[str] = []
    for session in sessions:
        session_id = normalize_strategy_session(session)
        if session_id and session_id not in normalized:
            normalized.append(session_id)
    return normalized


def is_strategy_session_active(params: dict[str, Any], when: datetime | None = None) -> bool:
    execution = params.get("execution") or {}
    sessions = normalize_strategy_sessions(list(execution.get("sessions") or []))
    if not sessions:
        return True

    when = when or datetime.now().astimezone()
    for session_id in sessions:
        session = _SESSION_BY_ID.get(session_id)
        if session and is_session_active(session, when):
            return True
    return False


def is_asset_trading_session_active(
    enabled_sessions: dict[str, bool] | None,
    when: datetime | None = None,
) -> bool:
    """Return True when forex trading is allowed for the current asset-settings session window."""
    sessions = normalize_enabled_sessions(enabled_sessions)
    if not any(sessions.values()):
        return False

    when = when or datetime.now().astimezone()
    if not is_forex_hours(when):
        return False

    for session_id, enabled in sessions.items():
        if not enabled:
            continue
        session = _SESSION_BY_ID.get(session_id)
        if session and is_session_active(session, when):
            return True
    return False


