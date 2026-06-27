from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "UTC"


def normalize_general_settings(
    *,
    timezone_auto: object = True,
    timezone: object = None,
    show_utc_times: object = False,
) -> dict[str, bool | str | None]:
    auto = True if timezone_auto is None else bool(timezone_auto)
    show_utc = False if show_utc_times is None else bool(show_utc_times)

    manual_tz: str | None = None
    if timezone is not None and str(timezone).strip():
        manual_tz = str(timezone).strip()

    if auto:
        return {
            "timezone_auto": True,
            "timezone": manual_tz,
            "show_utc_times": show_utc,
        }

    resolved = manual_tz if manual_tz and is_valid_timezone(manual_tz) else DEFAULT_TIMEZONE
    return {
        "timezone_auto": False,
        "timezone": resolved,
        "show_utc_times": show_utc,
    }


def is_valid_timezone(value: str) -> bool:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return False
    return True


def resolved_general_settings(raw: dict[str, object] | None) -> dict[str, bool | str | None]:
    if not raw:
        return normalize_general_settings()
    return normalize_general_settings(
        timezone_auto=raw.get("timezone_auto", True),
        timezone=raw.get("timezone"),
        show_utc_times=raw.get("show_utc_times", False),
    )
