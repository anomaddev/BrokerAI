from __future__ import annotations

from datetime import datetime, timezone


def format_oanda_time(value: datetime) -> str:
    """Format a UTC datetime as an OANDA candle open-time string."""
    if value.tzinfo is None:
        when = value.replace(tzinfo=timezone.utc)
    else:
        when = value.astimezone(timezone.utc)
    nanos = when.microsecond * 1000
    return when.strftime("%Y-%m-%dT%H:%M:%S.") + f"{nanos:09d}Z"


def parse_oanda_time(raw: str) -> datetime:
    """Parse an OANDA ISO-8601 candle time into UTC."""
    text = str(raw).strip().replace("Z", "+00:00")
    if "." in text:
        base, _, rest = text.partition(".")
        tz = ""
        if "+" in rest:
            frac, _, tz = rest.partition("+")
            tz = f"+{tz}"
        elif rest.count("-") > 0:
            frac, _, tz = rest.rpartition("-")
            tz = f"-{tz}"
        else:
            frac = rest
        text = f"{base}.{frac[:6]}{tz}"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
