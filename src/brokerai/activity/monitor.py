from __future__ import annotations

import logging
from datetime import datetime, timezone

from brokerai.activity.constants import (
    ACTION_CANDLE_CLOSED,
    ACTION_MARKET_SESSION_CLOSE,
    ACTION_MARKET_SESSION_OPEN,
)
from brokerai.activity.log import record_bot_activity
from brokerai.market_sessions import TRADING_SESSIONS, is_forex_hours, is_session_active

logger = logging.getLogger(__name__)

DEFAULT_CANDLE_MINUTES = 15


class ActivityMonitor:
    """Detect market session and candle boundaries for the activity timeline."""

    def __init__(self, *, candle_minutes: int = DEFAULT_CANDLE_MINUTES) -> None:
        self._candle_minutes = candle_minutes
        self._session_open: dict[str, bool] = {}
        self._last_candle_boundary_ms: int | None = None
        self._initialized = False

    async def tick(self, now: datetime | None = None) -> None:
        when = now or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        else:
            when = when.astimezone(timezone.utc)

        any_session_open = False

        for session in TRADING_SESSIONS:
            active = is_forex_hours(when) and is_session_active(session, when)
            if active:
                any_session_open = True

            previous = self._session_open.get(session.id)
            if previous is None:
                self._session_open[session.id] = active
                continue

            if active and not previous:
                await record_bot_activity(
                    ACTION_MARKET_SESSION_OPEN,
                    f"{session.name} open",
                    detail=f"{session.name} session opened",
                    source="activity_monitor",
                    metadata={"session_id": session.id, "session_name": session.name},
                    occurred_at=when,
                )
            elif not active and previous:
                await record_bot_activity(
                    ACTION_MARKET_SESSION_CLOSE,
                    f"{session.name} close",
                    detail=f"{session.name} session closed",
                    source="activity_monitor",
                    metadata={"session_id": session.id, "session_name": session.name},
                    occurred_at=when,
                )

            self._session_open[session.id] = active

        if not self._initialized:
            self._initialized = True
            if any_session_open:
                self._sync_candle_boundary(when)
            return

        if any_session_open:
            await self._maybe_record_candle(when)
        else:
            self._last_candle_boundary_ms = None

    def _sync_candle_boundary(self, when: datetime) -> None:
        duration_ms = self._candle_minutes * 60 * 1000
        now_ms = int(when.timestamp() * 1000)
        self._last_candle_boundary_ms = (now_ms // duration_ms) * duration_ms

    async def _maybe_record_candle(self, when: datetime) -> None:
        duration_ms = self._candle_minutes * 60 * 1000
        now_ms = int(when.timestamp() * 1000)
        boundary = (now_ms // duration_ms) * duration_ms

        if self._last_candle_boundary_ms is None:
            self._last_candle_boundary_ms = boundary
            return

        if boundary == self._last_candle_boundary_ms:
            return

        self._last_candle_boundary_ms = boundary
        label = f"{self._candle_minutes}m"
        await record_bot_activity(
            ACTION_CANDLE_CLOSED,
            f"Candle close ({label})",
            detail=f"{label} candle closed",
            source="activity_monitor",
            metadata={"timeframe_minutes": self._candle_minutes},
            occurred_at=when,
        )
