from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone


@dataclass(frozen=True)
class TradingSession:
    id: str
    name: str
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int


TRADING_SESSIONS: tuple[TradingSession, ...] = (
    TradingSession(id="asia", name="Asia", start_hour=0, start_minute=0, end_hour=9, end_minute=0),
    TradingSession(id="london", name="London", start_hour=7, start_minute=0, end_hour=16, end_minute=0),
    TradingSession(id="ny", name="NY", start_hour=13, start_minute=0, end_hour=22, end_minute=0),
)

TRADING_SESSION_IDS: tuple[str, ...] = tuple(session.id for session in TRADING_SESSIONS)


def default_market_indicators() -> dict[str, bool]:
    return {session_id: True for session_id in TRADING_SESSION_IDS}


def normalize_market_indicators(raw: object) -> dict[str, bool]:
    defaults = default_market_indicators()
    if not isinstance(raw, dict):
        return defaults
    return {session_id: bool(raw.get(session_id, True)) for session_id in TRADING_SESSION_IDS}


def _minutes_since_midnight(when: datetime) -> int:
    return when.hour * 60 + when.minute


def _format_utc_time(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%H:%M UTC")


def _format_utc_open(when: datetime) -> str:
    when_utc = when.astimezone(timezone.utc)
    return f"{when_utc.strftime('%a')} {_format_utc_time(when)}"


def session_hours_label(session: TradingSession) -> str:
    return (
        f"{session.start_hour:02d}:{session.start_minute:02d}"
        f"–{session.end_hour:02d}:{session.end_minute:02d} UTC"
    )


def is_forex_hours(when: datetime) -> bool:
    when_utc = when.astimezone(timezone.utc)
    weekday = when_utc.weekday()
    minutes = _minutes_since_midnight(when_utc)

    if weekday == 5:
        return False
    if weekday == 6 and minutes < 22 * 60:
        return False
    if weekday == 4 and minutes >= 22 * 60:
        return False
    return True


def is_session_active(session: TradingSession, when: datetime) -> bool:
    when_utc = when.astimezone(timezone.utc)
    current = _minutes_since_midnight(when_utc)
    start = session.start_hour * 60 + session.start_minute
    end = session.end_hour * 60 + session.end_minute
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def _session_open_at(session: TradingSession, on_date) -> datetime:
    return datetime.combine(
        on_date,
        time(session.start_hour, session.start_minute, tzinfo=timezone.utc),
    )


def _session_close_at(session: TradingSession, on_date) -> datetime:
    return datetime.combine(
        on_date,
        time(session.end_hour, session.end_minute, tzinfo=timezone.utc),
    )


def next_session_open(session: TradingSession, when: datetime) -> datetime | None:
    when_utc = when.astimezone(timezone.utc)
    for day_offset in range(8):
        open_at = _session_open_at(session, when_utc.date() + timedelta(days=day_offset))
        if open_at <= when_utc:
            continue
        if not is_forex_hours(open_at):
            continue
        return open_at
    return None


def current_session_close(session: TradingSession, when: datetime) -> datetime | None:
    when_utc = when.astimezone(timezone.utc)
    if not is_session_active(session, when_utc):
        return None
    close_at = _session_close_at(session, when_utc.date())
    if close_at > when_utc and is_forex_hours(when_utc):
        return close_at
    return None


def session_status(
    session: TradingSession,
    when: datetime,
    *,
    fx_open: bool,
    exchange_status: str | None = None,
) -> dict[str, str]:
    active = fx_open and is_session_active(session, when)
    status = "open" if active else "closed"
    payload: dict[str, str] = {
        "id": session.id,
        "name": session.name,
        "status": status,
        "hours": session_hours_label(session),
    }
    if exchange_status:
        payload["exchange_status"] = exchange_status

    close_at = current_session_close(session, when) if active else None
    if close_at is not None:
        payload["closes_at"] = close_at.isoformat()
        payload["closes_at_label"] = _format_utc_time(close_at)
    else:
        next_open = next_session_open(session, when)
        if next_open is not None:
            payload["next_open"] = next_open.isoformat()
            payload["next_open_label"] = _format_utc_open(next_open)

    return payload
