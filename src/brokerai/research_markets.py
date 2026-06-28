from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_DAILY_REPORT_MARKET_ID = "london"
DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS = -2
MIN_DAILY_REPORT_MARKET_OFFSET_HOURS = -6
MAX_DAILY_REPORT_MARKET_OFFSET_HOURS = 6

DEFAULT_WEEKLY_BRIEF_MARKET_ID = "london"
DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS = -1
DEFAULT_WEEKLY_DEBRIEF_MARKET_ID = "london"
DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS = 1


@dataclass(frozen=True)
class ResearchMarket:
    id: str
    name: str
    label: str
    timezone: str
    open_time: time
    close_time: time


RESEARCH_MARKETS: tuple[ResearchMarket, ...] = (
    ResearchMarket(
        id="london",
        name="London",
        label="London (LSE / FX)",
        timezone="Europe/London",
        open_time=time(8, 0),
        close_time=time(17, 0),
    ),
    ResearchMarket(
        id="new_york",
        name="New York",
        label="New York (NYSE)",
        timezone="America/New_York",
        open_time=time(9, 30),
        close_time=time(16, 0),
    ),
    ResearchMarket(
        id="tokyo",
        name="Tokyo",
        label="Tokyo (TSE)",
        timezone="Asia/Tokyo",
        open_time=time(9, 0),
        close_time=time(15, 0),
    ),
    ResearchMarket(
        id="sydney",
        name="Sydney",
        label="Sydney (ASX)",
        timezone="Australia/Sydney",
        open_time=time(10, 0),
        close_time=time(16, 0),
    ),
    ResearchMarket(
        id="frankfurt",
        name="Frankfurt",
        label="Frankfurt (Xetra)",
        timezone="Europe/Berlin",
        open_time=time(9, 0),
        close_time=time(17, 30),
    ),
    ResearchMarket(
        id="hong_kong",
        name="Hong Kong",
        label="Hong Kong (HKEX)",
        timezone="Asia/Hong_Kong",
        open_time=time(9, 30),
        close_time=time(16, 0),
    ),
)

_MARKET_BY_ID = {market.id: market for market in RESEARCH_MARKETS}


def get_market(market_id: str) -> ResearchMarket | None:
    return _MARKET_BY_ID.get(market_id)


def normalize_market_id(market_id: str | None) -> str:
    if market_id and market_id in _MARKET_BY_ID:
        return market_id
    return DEFAULT_DAILY_REPORT_MARKET_ID


def normalize_market_offset_hours(offset: int | None) -> int:
    if offset is None:
        return DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS
    return max(
        MIN_DAILY_REPORT_MARKET_OFFSET_HOURS,
        min(MAX_DAILY_REPORT_MARKET_OFFSET_HOURS, int(offset)),
    )


def iso_week_key(d: date) -> str:
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def list_schedule_markets() -> list[dict[str, str]]:
    return [
        {
            "id": market.id,
            "name": market.name,
            "label": market.label,
            "timezone": market.timezone,
            "open_time_local": market.open_time.strftime("%H:%M"),
            "close_time_local": market.close_time.strftime("%H:%M"),
        }
        for market in RESEARCH_MARKETS
    ]


def market_open_utc(market_id: str, on: date) -> datetime:
    market = get_market(normalize_market_id(market_id))
    assert market is not None
    tz = ZoneInfo(market.timezone)
    local_open = datetime.combine(on, market.open_time, tzinfo=tz)
    return local_open.astimezone(timezone.utc)


def market_close_utc(market_id: str, on: date) -> datetime:
    market = get_market(normalize_market_id(market_id))
    assert market is not None
    tz = ZoneInfo(market.timezone)
    local_close = datetime.combine(on, market.close_time, tzinfo=tz)
    return local_close.astimezone(timezone.utc)


def week_end_close_date(week_start: date, market_id: str) -> date:
    """Friday of the ISO week containing week_start (Monday)."""
    _ = market_id  # reserved for future market-local week boundaries
    return week_start + timedelta(days=4)


def week_open_date(d: date) -> date:
    """Monday of the week containing *d* (Mon–Fri). Sat/Sun roll forward to next Monday."""
    if d.weekday() >= 5:
        return d + timedelta(days=7 - d.weekday())
    return d - timedelta(days=d.weekday())


def _utc_now(now: datetime | None = None) -> datetime:
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        return ref.replace(tzinfo=timezone.utc)
    return ref.astimezone(timezone.utc)


def market_local_date(market_id: str, now: datetime) -> date:
    market = get_market(normalize_market_id(market_id))
    assert market is not None
    return _utc_now(now).astimezone(ZoneInfo(market.timezone)).date()


def weekly_brief_run_date(market_id: str, now: datetime | None = None) -> date:
    """Monday (week open) for the weekly brief in the chosen market's calendar."""
    ref = _utc_now(now)
    local_today = market_local_date(market_id, ref)
    return week_open_date(local_today)


def scheduled_weekly_brief_run_utc(
    market_id: str,
    offset_hours: int,
    *,
    now: datetime | None = None,
) -> datetime:
    """Scheduled weekly brief time for the current target week (Monday open + offset)."""
    ref = _utc_now(now)
    run_day = weekly_brief_run_date(market_id, ref)
    return scheduled_run_utc(market_id, offset_hours, on=run_day)


def next_weekly_brief_run_utc(
    market_id: str,
    offset_hours: int,
    *,
    now: datetime | None = None,
) -> datetime:
    """Next weekly brief run (rolls forward after this week's slot has passed)."""
    ref = _utc_now(now)
    run_day = weekly_brief_run_date(market_id, ref)
    scheduled = scheduled_run_utc(market_id, offset_hours, on=run_day)
    if ref >= scheduled:
        run_day = run_day + timedelta(days=7)
        scheduled = scheduled_run_utc(market_id, offset_hours, on=run_day)
    return scheduled


def scheduled_run_utc(
    market_id: str,
    offset_hours: int,
    *,
    on: date | None = None,
    now: datetime | None = None,
) -> datetime:
    market = get_market(normalize_market_id(market_id))
    assert market is not None
    if on is None:
        ref = now or datetime.now(timezone.utc)
        on = ref.astimezone(ZoneInfo(market.timezone)).date()
    offset = normalize_market_offset_hours(offset_hours)
    return market_open_utc(market.id, on) + timedelta(hours=offset)


def scheduled_close_run_utc(
    market_id: str,
    offset_hours: int,
    *,
    on: date | None = None,
    now: datetime | None = None,
) -> datetime:
    market = get_market(normalize_market_id(market_id))
    assert market is not None
    if on is None:
        ref = now or datetime.now(timezone.utc)
        on = ref.astimezone(ZoneInfo(market.timezone)).date()
    offset = normalize_market_offset_hours(offset_hours)
    return market_close_utc(market.id, on) + timedelta(hours=offset)


def weekly_debrief_close_date(market_id: str, now: datetime | None = None) -> date:
    """Friday ending the debrief target week in the chosen market's calendar."""
    ref = _utc_now(now)
    local_today = market_local_date(market_id, ref)
    week_start = week_open_date(local_today)
    return week_end_close_date(week_start, market_id)


def scheduled_weekly_debrief_run_utc(
    market_id: str,
    offset_hours: int,
    *,
    now: datetime | None = None,
) -> datetime:
    """Scheduled debrief time for the current target week (Friday close + offset)."""
    close_day = weekly_debrief_close_date(market_id, now)
    return scheduled_close_run_utc(market_id, offset_hours, on=close_day)


def next_weekly_debrief_run_utc(
    market_id: str,
    offset_hours: int,
    *,
    now: datetime | None = None,
) -> datetime:
    """Next weekly debrief run (rolls forward after this week's slot has passed)."""
    ref = _utc_now(now)
    close_day = weekly_debrief_close_date(market_id, ref)
    scheduled = scheduled_close_run_utc(market_id, offset_hours, on=close_day)
    if ref >= scheduled:
        close_day = close_day + timedelta(days=7)
        scheduled = scheduled_close_run_utc(market_id, offset_hours, on=close_day)
    return scheduled


def next_weekly_debrief_close_date(
    market_id: str,
    offset_hours: int,
    *,
    now: datetime | None = None,
) -> date:
    """Friday date for the next debrief run."""
    ref = _utc_now(now)
    close_day = weekly_debrief_close_date(market_id, ref)
    scheduled = scheduled_close_run_utc(market_id, offset_hours, on=close_day)
    if ref >= scheduled:
        close_day = close_day + timedelta(days=7)
    return close_day


def scheduled_weekly_debrief_utc(
    week_start: date,
    market_id: str,
    offset_hours: int,
) -> datetime:
    """Scheduled debrief time for a specific week (Friday close + offset)."""
    close_day = week_end_close_date(week_start, market_id)
    return scheduled_close_run_utc(market_id, offset_hours, on=close_day)


def is_past_scheduled_run(
    now: datetime,
    market_id: str,
    offset_hours: int,
) -> bool:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    scheduled = scheduled_run_utc(market_id, offset_hours, now=now)
    return now >= scheduled


def is_past_weekly_brief_run(
    now: datetime,
    market_id: str,
    offset_hours: int,
) -> bool:
    ref = _utc_now(now)
    scheduled = scheduled_weekly_brief_run_utc(market_id, offset_hours, now=ref)
    return ref >= scheduled


def is_past_weekly_debrief_run(
    now: datetime,
    week_start: date,
    market_id: str,
    offset_hours: int,
) -> bool:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    scheduled = scheduled_weekly_debrief_utc(week_start, market_id, offset_hours)
    return now >= scheduled


def _offset_label(offset: int, *, anchor: str) -> str:
    if offset == 0:
        return f"at market {anchor}"
    if offset < 0:
        hours = abs(offset)
        unit = "hour" if hours == 1 else "hours"
        return f"{hours} {unit} before {anchor}"
    unit = "hour" if offset == 1 else "hours"
    return f"{offset} {unit} after {anchor}"


def describe_schedule(market_id: str, offset_hours: int) -> str:
    market = get_market(normalize_market_id(market_id))
    assert market is not None
    offset = normalize_market_offset_hours(offset_hours)
    open_label = market.open_time.strftime("%H:%M")
    offset_label = _offset_label(offset, anchor="open")

    scheduled = scheduled_run_utc(market.id, offset)
    run_utc = scheduled.strftime("%H:%M UTC")
    return (
        f"{offset_label} ({market.label}, opens {open_label} {market.timezone}) — "
        f"today ~{run_utc}"
    )


def describe_weekly_brief_schedule(market_id: str, offset_hours: int) -> str:
    market = get_market(normalize_market_id(market_id))
    assert market is not None
    offset = normalize_market_offset_hours(offset_hours)
    open_label = market.open_time.strftime("%H:%M")
    offset_label = _offset_label(offset, anchor="open")

    now = datetime.now(timezone.utc)
    scheduled = next_weekly_brief_run_utc(market.id, offset, now=now)
    run_day = weekly_brief_run_date(market.id, now)
    if now >= scheduled_run_utc(market.id, offset, on=run_day):
        run_day = run_day + timedelta(days=7)
    run_utc = scheduled.strftime("%H:%M UTC")
    return (
        f"{offset_label} ({market.label}, opens {open_label} {market.timezone}) — "
        f"~{run_utc} · week open {run_day.isoformat()}"
    )


def describe_close_schedule(market_id: str, offset_hours: int, *, week_start: date | None = None) -> str:
    market = get_market(normalize_market_id(market_id))
    assert market is not None
    offset = normalize_market_offset_hours(offset_hours)
    close_label = market.close_time.strftime("%H:%M")
    offset_label = _offset_label(offset, anchor="close")

    if week_start is None:
        now = datetime.now(timezone.utc)
        scheduled = next_weekly_debrief_run_utc(market.id, offset, now=now)
        close_day = next_weekly_debrief_close_date(market.id, offset, now=now)
    else:
        close_day = week_end_close_date(week_start, market.id)
        scheduled = scheduled_close_run_utc(market.id, offset, on=close_day)
    run_utc = scheduled.strftime("%H:%M UTC")
    return (
        f"{offset_label} ({market.label}, closes {close_label} {market.timezone}) — "
        f"~{run_utc} · week ending {close_day.isoformat()}"
    )


def detect_schedule_conflict(
    *,
    daily_market_id: str,
    daily_offset_hours: int,
    brief_market_id: str,
    brief_offset_hours: int,
    on: date | None = None,
) -> str | None:
    """Warn when the weekly brief would run before the daily report on the same day.

    Equal run times are allowed; the scheduler always runs the daily report first.
    """
    daily_market = get_market(normalize_market_id(daily_market_id))
    brief_market = get_market(normalize_market_id(brief_market_id))
    if daily_market is None or brief_market is None:
        return None

    ref = datetime.now(timezone.utc)
    if on is None:
        on = weekly_brief_run_date(brief_market.id, ref)

    daily_utc = scheduled_run_utc(daily_market.id, daily_offset_hours, on=on)
    brief_utc = scheduled_run_utc(brief_market.id, brief_offset_hours, on=on)

    if brief_utc < daily_utc:
        daily_time = daily_utc.strftime("%H:%M UTC")
        brief_time = brief_utc.strftime("%H:%M UTC")
        return (
            f"Weekly brief is scheduled at {brief_time}, before the daily report at "
            f"{daily_time} on {on.isoformat()}. The brief should run after the daily "
            f"report so it can include that day's analysis."
        )
    return None


def should_defer_weekly_brief_for_daily(
    now: datetime,
    *,
    daily_report_enabled: bool,
    daily_market_id: str,
    daily_offset_hours: int,
    brief_market_id: str,
    brief_offset_hours: int,
    daily_completed_today: bool,
) -> bool:
    """Return True when the weekly brief must wait for today's daily report to finish."""
    if not daily_report_enabled or daily_completed_today:
        return False

    ref = _utc_now(now)
    on = weekly_brief_run_date(brief_market_id, ref)
    daily_utc = scheduled_run_utc(daily_market_id, daily_offset_hours, on=on)
    brief_utc = scheduled_run_utc(brief_market_id, brief_offset_hours, on=on)

    if brief_utc < daily_utc:
        return False

    return ref >= daily_utc


def collect_schedule_warnings(
    *,
    daily_report_enabled: bool,
    daily_report_market_id: str,
    daily_report_market_offset_hours: int,
    weekly_brief_enabled: bool,
    weekly_brief_market_id: str,
    weekly_brief_market_offset_hours: int,
) -> list[str]:
    warnings: list[str] = []
    if not daily_report_enabled or not weekly_brief_enabled:
        return warnings
    conflict = detect_schedule_conflict(
        daily_market_id=daily_report_market_id,
        daily_offset_hours=daily_report_market_offset_hours,
        brief_market_id=weekly_brief_market_id,
        brief_offset_hours=weekly_brief_market_offset_hours,
    )
    if conflict:
        warnings.append(conflict)
    return warnings
