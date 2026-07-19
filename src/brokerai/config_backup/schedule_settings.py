from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from brokerai.auth.general_settings import is_valid_timezone
from brokerai.auth.store import AuthStore
from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import BackupSettingsRow
from brokerai.research_markets import (
    DEFAULT_DAILY_REPORT_MARKET_ID,
    DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
    list_schedule_markets,
    normalize_market_id,
    normalize_market_offset_hours,
    scheduled_run_utc,
)

SINGLETON_ID = "default"
COLLECTION = "backup_settings"

BackupScheduleMode = Literal["daily", "daily_time", "interval"]

DEFAULT_DAILY_TIME = "02:00"
_DAILY_TIME_RE = re.compile(r"^(\d{1,2}):(\d{1,2})$")

FULL_RETENTION_MIN = 5
FULL_RETENTION_MAX = 50
FULL_RETENTION_STEP = 5
CHANGE_RETENTION_MIN = 20
CHANGE_RETENTION_MAX = 100
CHANGE_RETENTION_STEP = 5

DEFAULT_BACKUP_SCHEDULE: dict[str, Any] = {
    "id": SINGLETON_ID,
    "enabled": False,
    "mode": "daily",
    "daily_market_id": DEFAULT_DAILY_REPORT_MARKET_ID,
    "daily_offset_hours": DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
    "daily_time": DEFAULT_DAILY_TIME,
    "interval_hours": 24,
    "full_retention": 30,
    "change_retention": 100,
    "last_scheduled_at": None,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_daily_time(value: object) -> str:
    """Normalize a local run time to ``HH:MM`` (24-hour)."""
    if value is None:
        return DEFAULT_DAILY_TIME
    text = str(value).strip()
    match = _DAILY_TIME_RE.match(text)
    if not match:
        return DEFAULT_DAILY_TIME
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return DEFAULT_DAILY_TIME
    return f"{hour:02d}:{minute:02d}"


def _snap_retention(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
    step: int,
) -> int:
    """Clamp *value* to range and snap to the nearest allowed step."""
    try:
        raw = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raw = default
    clamped = max(minimum, min(maximum, raw))
    offset = clamped - minimum
    snapped = minimum + round(offset / step) * step
    return max(minimum, min(maximum, snapped))


def normalize_full_retention(value: object) -> int:
    """Full backup retention count (5–50 in steps of 5)."""
    return _snap_retention(
        value,
        default=DEFAULT_BACKUP_SCHEDULE["full_retention"],
        minimum=FULL_RETENTION_MIN,
        maximum=FULL_RETENTION_MAX,
        step=FULL_RETENTION_STEP,
    )


def normalize_change_retention(value: object) -> int:
    """Change history retention count (20–100 in steps of 5)."""
    return _snap_retention(
        value,
        default=DEFAULT_BACKUP_SCHEDULE["change_retention"],
        minimum=CHANGE_RETENTION_MIN,
        maximum=CHANGE_RETENTION_MAX,
        step=CHANGE_RETENTION_STEP,
    )


def resolve_user_schedule_timezone() -> str:
    """Timezone used for daily_time scheduling (from General settings)."""
    user = AuthStore().get_user()
    if user is None:
        return "UTC"
    general = user.resolved_general_settings()
    tz = general.get("timezone")
    if isinstance(tz, str) and tz.strip() and is_valid_timezone(tz.strip()):
        return tz.strip()
    return "UTC"


def scheduled_local_time_utc(
    daily_time: str,
    timezone_name: str,
    *,
    on: date | None = None,
    now: datetime | None = None,
) -> datetime:
    """Return the UTC instant for *daily_time* on *on* in *timezone_name*."""
    tz_name = timezone_name if is_valid_timezone(timezone_name) else "UTC"
    tz = ZoneInfo(tz_name)
    ref = now or _now()
    local_date = on or ref.astimezone(tz).date()
    normalized = normalize_daily_time(daily_time)
    hour, minute = (int(part) for part in normalized.split(":"))
    local_dt = datetime.combine(local_date, time(hour, minute), tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


def normalize_schedule_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(DEFAULT_BACKUP_SCHEDULE)
    if not raw:
        return base

    base["enabled"] = bool(raw.get("enabled", False))
    mode = str(raw.get("mode") or "daily").strip().lower()
    base["mode"] = mode if mode in {"daily", "daily_time", "interval"} else "daily"
    base["daily_market_id"] = normalize_market_id(str(raw.get("daily_market_id") or ""))
    base["daily_offset_hours"] = normalize_market_offset_hours(raw.get("daily_offset_hours"))
    base["daily_time"] = normalize_daily_time(raw.get("daily_time"))
    interval = int(raw.get("interval_hours") or 24)
    base["interval_hours"] = max(1, min(48, interval))
    base["full_retention"] = normalize_full_retention(raw.get("full_retention"))
    base["change_retention"] = normalize_change_retention(raw.get("change_retention"))

    last = raw.get("last_scheduled_at")
    if isinstance(last, datetime):
        base["last_scheduled_at"] = last.isoformat()
    elif isinstance(last, str) and last.strip():
        base["last_scheduled_at"] = last.strip()
    else:
        base["last_scheduled_at"] = None

    return base


def schedule_settings_payload(settings: dict[str, Any]) -> dict[str, Any]:
    """API response including schedule market catalog."""
    normalized = normalize_schedule_settings(settings)
    tz = resolve_user_schedule_timezone()
    return {
        **normalized,
        "schedule_markets": list_schedule_markets(),
        "schedule_timezone": tz,
    }


async def get_backup_schedule_settings() -> dict[str, Any]:
    async with session_scope() as session:
        row = await session.get(BackupSettingsRow, SINGLETON_ID)
        return normalize_schedule_settings(dict(row.doc) if row else None)


async def save_backup_schedule_settings(updates: dict[str, Any]) -> dict[str, Any]:
    current = await get_backup_schedule_settings()
    merged = normalize_schedule_settings({**current, **updates, "id": SINGLETON_ID})
    async with session_scope() as session:
        row = await session.get(BackupSettingsRow, SINGLETON_ID)
        if row is None:
            session.add(BackupSettingsRow(id=SINGLETON_ID, doc=merged))
        else:
            row.doc = merged
    return merged


def _scheduled_run_for_settings(
    settings: dict[str, Any],
    *,
    now: datetime | None = None,
) -> datetime:
    """UTC instant when today's scheduled backup should run."""
    normalized = normalize_schedule_settings(settings)
    ref = now or _now()
    mode = normalized["mode"]

    if mode == "daily_time":
        return scheduled_local_time_utc(
            str(normalized["daily_time"]),
            resolve_user_schedule_timezone(),
            now=ref,
        )

    return scheduled_run_utc(
        str(normalized["daily_market_id"]),
        int(normalized["daily_offset_hours"]),
        on=ref.date(),
    )


def is_scheduled_backup_due(
    settings: dict[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    """Return True when an automatic full backup should run."""
    normalized = normalize_schedule_settings(settings)
    if not normalized.get("enabled"):
        return False

    ref = now or _now()
    mode = normalized["mode"]

    if mode == "interval":
        last_raw = normalized.get("last_scheduled_at")
        if not last_raw:
            return True
        try:
            last = datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
        except ValueError:
            return True
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        interval = timedelta(hours=int(normalized["interval_hours"]))
        return ref >= last + interval

    scheduled = _scheduled_run_for_settings(normalized, now=ref)
    if ref < scheduled:
        return False

    last_raw = normalized.get("last_scheduled_at")
    if not last_raw:
        return True
    try:
        last = datetime.fromisoformat(str(last_raw).replace("Z", "+00:00"))
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return last < scheduled


async def mark_scheduled_backup_ran(*, when: datetime | None = None) -> None:
    stamp = (when or _now()).isoformat()
    async with session_scope() as session:
        row = await session.get(BackupSettingsRow, SINGLETON_ID)
        if row is None:
            doc = normalize_schedule_settings({"id": SINGLETON_ID, "last_scheduled_at": stamp})
            session.add(BackupSettingsRow(id=SINGLETON_ID, doc=doc))
        else:
            doc = dict(row.doc)
            doc["last_scheduled_at"] = stamp
            row.doc = doc
