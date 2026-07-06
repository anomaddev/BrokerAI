from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = timezone.utc

_APAC_SESSION_IDS: tuple[str, ...] = ("sydney", "asia")
_LEGACY_APAC_KEYS: tuple[str, ...] = ("tokyo", "singapore")


@dataclass(frozen=True)
class TradingSession:
    id: str
    name: str
    timezone: str
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    coverage: str | None = None


TRADING_SESSIONS: tuple[TradingSession, ...] = (
    TradingSession(
        id="sydney",
        name="Sydney",
        timezone="America/New_York",
        start_hour=17,
        start_minute=0,
        end_hour=2,
        end_minute=0,
    ),
    TradingSession(
        id="asia",
        name="Asia",
        timezone="UTC",
        start_hour=0,
        start_minute=0,
        end_hour=9,
        end_minute=0,
        coverage="Tokyo · Singapore · Hong Kong · China",
    ),
    TradingSession(
        id="london",
        name="London",
        timezone="America/New_York",
        start_hour=3,
        start_minute=0,
        end_hour=12,
        end_minute=0,
    ),
    TradingSession(
        id="ny",
        name="NY",
        timezone="America/New_York",
        start_hour=8,
        start_minute=0,
        end_hour=17,
        end_minute=0,
    ),
)

TRADING_SESSION_IDS: tuple[str, ...] = tuple(session.id for session in TRADING_SESSIONS)

_SESSION_BY_ID = {session.id: session for session in TRADING_SESSIONS}

_STATIC_HOURS_LABELS: dict[str, str] = {
    "sydney": "5:00 PM–2:00 AM ET",
    "asia": "12:00 AM–9:00 AM UTC",
    "london": "3:00 AM–12:00 PM ET",
    "ny": "8:00 AM–5:00 PM ET",
}


def default_market_indicators() -> dict[str, bool]:
    return {session_id: True for session_id in TRADING_SESSION_IDS}


def _migrate_legacy_apac_flags(raw: dict) -> dict[str, bool]:
    """Map legacy tokyo/singapore/old-asia toggles onto the current session IDs."""
    merged = dict(default_market_indicators())

    if "asia" in raw:
        asia_enabled = bool(raw["asia"])
        for session_id in _APAC_SESSION_IDS:
            if session_id not in raw:
                merged[session_id] = asia_enabled

    if "asia" not in raw:
        legacy_apac: bool | None = None
        for legacy_key in _LEGACY_APAC_KEYS:
            if legacy_key in raw:
                enabled = bool(raw[legacy_key])
                legacy_apac = enabled if legacy_apac is None else (legacy_apac or enabled)
        if legacy_apac is not None:
            merged["asia"] = legacy_apac

    return merged


def normalize_market_indicators(raw: object) -> dict[str, bool]:
    defaults = default_market_indicators()
    if not isinstance(raw, dict):
        return defaults

    merged = _migrate_legacy_apac_flags(raw)
    return {
        session_id: bool(raw.get(session_id, merged[session_id]))
        for session_id in TRADING_SESSION_IDS
    }


def default_enabled_sessions() -> dict[str, bool]:
    """Default forex trading sessions (all enabled)."""
    return default_market_indicators()


def normalize_enabled_sessions(raw: object) -> dict[str, bool]:
    """Normalize forex asset-settings session toggles."""
    return normalize_market_indicators(raw)


def _session_tzinfo(session: TradingSession) -> ZoneInfo:
    return ZoneInfo(session.timezone)


def _local_minutes(when: datetime, session: TradingSession) -> int:
    local = when.astimezone(_session_tzinfo(session))
    return local.hour * 60 + local.minute


def _format_time_label(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%H:%M UTC")


def _format_open_label(when: datetime) -> str:
    when_utc = when.astimezone(UTC)
    return f"{when_utc.strftime('%a')} {_format_time_label(when)}"


def session_hours_label(session: TradingSession) -> str:
    return _STATIC_HOURS_LABELS.get(session.id, "")


def session_definition_payload(session: TradingSession) -> dict[str, str | int | None]:
    payload: dict[str, str | int | None] = {
        "id": session.id,
        "name": session.name,
        "timezone": session.timezone,
        "hours": session_hours_label(session),
        "start_hour": session.start_hour,
        "start_minute": session.start_minute,
        "end_hour": session.end_hour,
        "end_minute": session.end_minute,
        "coverage": session.coverage,
    }
    return payload


def is_forex_hours(when: datetime) -> bool:
    """Return True when the spot FX market is open (OANDA America/New_York calendar)."""
    from brokerai.trading.data.market_calendar import is_forex_open

    return is_forex_open(when)


def is_session_active(session: TradingSession, when: datetime) -> bool:
    current = _local_minutes(when, session)
    start = session.start_hour * 60 + session.start_minute
    end = session.end_hour * 60 + session.end_minute
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def _combine_local(session: TradingSession, on_date: date) -> datetime:
    return datetime.combine(
        on_date,
        time(session.start_hour, session.start_minute),
        tzinfo=_session_tzinfo(session),
    )


def _combine_local_close(session: TradingSession, on_date: date) -> datetime:
    return datetime.combine(
        on_date,
        time(session.end_hour, session.end_minute),
        tzinfo=_session_tzinfo(session),
    )


def next_session_open(session: TradingSession, when: datetime) -> datetime | None:
    tz = _session_tzinfo(session)
    when_local = when.astimezone(tz)
    for day_offset in range(8):
        open_local = _combine_local(session, when_local.date() + timedelta(days=day_offset))
        if open_local <= when:
            continue
        if not is_forex_hours(open_local):
            continue
        return open_local.astimezone(UTC)
    return None


def current_session_close(session: TradingSession, when: datetime) -> datetime | None:
    if not is_session_active(session, when):
        return None

    tz = _session_tzinfo(session)
    when_local = when.astimezone(tz)
    current = when_local.hour * 60 + when_local.minute
    start = session.start_hour * 60 + session.start_minute
    end = session.end_hour * 60 + session.end_minute

    if start <= end:
        close_date = when_local.date()
    elif current >= start:
        close_date = when_local.date() + timedelta(days=1)
    else:
        close_date = when_local.date()

    close_local = _combine_local_close(session, close_date)
    if close_local > when and is_forex_hours(when):
        return close_local.astimezone(UTC)
    return None


def _parse_exchange_open(exchange_status: str | None) -> bool | None:
    if not exchange_status:
        return None
    normalized = exchange_status.strip().lower()
    if normalized in ("open", "extended-hours"):
        return True
    if normalized == "closed":
        return False
    return None


def session_status(
    session: TradingSession,
    when: datetime,
    *,
    fx_open: bool,
    exchange_status: str | None = None,
) -> dict[str, str]:
    exchange_open = _parse_exchange_open(exchange_status)
    if exchange_open is not None:
        active = exchange_open
    else:
        active = fx_open and is_forex_hours(when) and is_session_active(session, when)
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
        payload["closes_at_label"] = _format_time_label(close_at)
    else:
        next_open = next_session_open(session, when)
        if next_open is not None:
            payload["next_open"] = next_open.isoformat()
            payload["next_open_label"] = _format_open_label(next_open)

    return payload


def get_session(session_id: str) -> TradingSession | None:
    return _SESSION_BY_ID.get(session_id)
