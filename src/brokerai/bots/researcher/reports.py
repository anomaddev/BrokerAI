"""Research report keys, metadata parsing, and store-backed I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from itertools import islice

from brokerai.bots.researcher.report_store import get_report_store, local_reports_dir


@dataclass
class ReportMeta:
    filename: str
    date: str
    report_type: str
    path: str
    model_label: str | None = None
    generated_at: str | None = None
    reasoning_effort: str | None = None
    size_bytes: int = 0


_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")
_WEEK_FOLDER_RE = re.compile(r"^(\d{4})_(\d{1,2})$")
_WEEKLY_BRIEF_RE = re.compile(r"^weekly_brief_(\d{1,2})\.md$")
_WEEKLY_DEBRIEF_RE = re.compile(r"^weekly_debrief_(\d{1,2})\.md$")

_MODEL_NAME_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")
_SYNTHESIS_REASONING_RE = re.compile(r"reasoning\s+(\w+)")
_DAILY_MODEL_SLUG_RE = re.compile(r"-daily_(.+)\.md$")


def _strip_model_name(value: str) -> str:
    """Drop the trailing technical model name, e.g. 'Grok 4.3 (grok-4.3)' -> 'Grok 4.3'."""
    return _MODEL_NAME_SUFFIX_RE.sub("", value).strip()


def _model_label_from_filename(name: str) -> str | None:
    match = _DAILY_MODEL_SLUG_RE.search(name)
    if not match:
        return None
    return match.group(1).replace("-", " ")


def parse_report_header_text(content: str) -> dict[str, str | None]:
    """Extract display metadata from the leading lines of report markdown."""
    info: dict[str, str | None] = {
        "model_label": None,
        "generated_at": None,
        "reasoning_effort": None,
    }
    head = list(islice(content.splitlines(), 15))
    for raw in head:
        line = raw.strip()
        if line.startswith("Generated at "):
            info["generated_at"] = line[len("Generated at ") :].strip() or None
        elif line.startswith("Synthesis model:"):
            rest = line[len("Synthesis model:") :].strip()
            label, _, effort = rest.partition("·")
            info["model_label"] = _strip_model_name(label) or None
            reasoning = _SYNTHESIS_REASONING_RE.search(effort)
            if reasoning:
                info["reasoning_effort"] = reasoning.group(1)
        elif line.startswith("Contributing models:"):
            rest = line[len("Contributing models:") :].strip()
            if rest and rest != "—" and not info.get("model_label"):
                info["model_label"] = rest
        elif line.startswith("Model:"):
            info["model_label"] = _strip_model_name(line[len("Model:") :]) or None
        elif line.startswith("Reasoning effort:"):
            info["reasoning_effort"] = line[len("Reasoning effort:") :].strip() or None
    return info


def _build_meta_from_key(
    key: str,
    *,
    content: str | None = None,
    size_bytes: int = 0,
) -> ReportMeta | None:
    parts = key.replace("\\", "/").split("/")
    name = parts[-1]
    parent = parts[-2] if len(parts) > 1 else ""

    daily_match = _FILENAME_RE.match(name)
    report_date: str | None = None
    report_type: str | None = None

    if daily_match and daily_match.group(2) == "daily":
        report_date = daily_match.group(1)
        report_type = "daily"
    elif daily_match and daily_match.group(2).startswith("daily_"):
        report_date = daily_match.group(1)
        report_type = "daily_model"
    else:
        weekly_brief_match = _WEEKLY_BRIEF_RE.match(name)
        weekly_debrief_match = _WEEKLY_DEBRIEF_RE.match(name)
        folder_match = _WEEK_FOLDER_RE.match(parent) if parent else None
        if weekly_brief_match and folder_match:
            week_start = date.fromisocalendar(
                int(folder_match.group(1)), int(folder_match.group(2)), 1
            )
            report_date = week_start.isoformat()
            report_type = "weekly_brief"
        elif weekly_debrief_match and folder_match:
            week_start = date.fromisocalendar(
                int(folder_match.group(1)), int(folder_match.group(2)), 1
            )
            report_date = week_start.isoformat()
            report_type = "weekly_debrief"
        elif daily_match:
            report_date = daily_match.group(1)
            report_type = daily_match.group(2)

    if not report_date or not report_type:
        return None

    header = parse_report_header_text(content or "")
    model_label = header.get("model_label")
    if not model_label and report_type == "daily_model":
        model_label = _model_label_from_filename(name)
    if content is not None and size_bytes <= 0:
        size_bytes = len(content.encode("utf-8"))

    store = get_report_store()
    path = (
        f"storage://research-reports/{key}"
        if store.uses_storage
        else str(local_reports_dir() / key)
    )
    return ReportMeta(
        filename=key,
        date=report_date,
        report_type=report_type,
        path=path,
        model_label=model_label,
        generated_at=header.get("generated_at"),
        reasoning_effort=header.get("reasoning_effort"),
        size_bytes=size_bytes,
    )


def reports_dir():
    """Legacy helper: local reports directory (filesystem fallback / migrate source)."""
    return local_reports_dir()


def _as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def resolve_weekly_target_date(d: str | date) -> date:
    """Monday of the week a daily report belongs to.

    Mon-Fri map to the current week's Monday. Saturday and Sunday (market
    closed) roll forward to the next Monday so weekend analysis feeds the
    upcoming week's debrief.
    """
    d = _as_date(d)
    if d.weekday() >= 5:  # Saturday or Sunday
        return d + timedelta(days=7 - d.weekday())
    return d - timedelta(days=d.weekday())


def week_folder_key(d: str | date) -> tuple[int, int]:
    """ISO (year, week) for the report's target week folder."""
    week_start = resolve_weekly_target_date(d)
    iso_year, iso_week, _ = week_start.isocalendar()
    return iso_year, iso_week


def week_start_from_folder_name(folder_name: str) -> date | None:
    match = _WEEK_FOLDER_RE.match(folder_name)
    if not match:
        return None
    return date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)


@dataclass
class DailyReportEntry:
    date: str
    content: str


def week_key_prefix(d: str | date) -> str:
    iso_year, iso_week = week_folder_key(d)
    return f"{iso_year}_{iso_week}"


def daily_report_key(report_date: str | date) -> str:
    d = _as_date(report_date)
    return f"{week_key_prefix(d)}/{d.isoformat()}-daily.md"


def daily_model_report_key(report_date: str | date, slug: str) -> str:
    d = _as_date(report_date)
    return f"{week_key_prefix(d)}/{d.isoformat()}-daily_{slug}.md"


def weekly_brief_key(week_start: date) -> str:
    iso_year, iso_week, _ = week_start.isocalendar()
    return f"{iso_year}_{iso_week}/weekly_brief_{iso_week}.md"


def weekly_debrief_key(week_start: date) -> str:
    iso_year, iso_week, _ = week_start.isocalendar()
    return f"{iso_year}_{iso_week}/weekly_debrief_{iso_week}.md"


# Back-compat Path-like helpers used by weekly.py (return key strings cast via Path wrappers).
def weekly_brief_path(week_start: date):
    from pathlib import Path

    return Path(weekly_brief_key(week_start))


def weekly_debrief_path(week_start: date):
    from pathlib import Path

    return Path(weekly_debrief_key(week_start))


def daily_report_path(report_date: str | date):
    from pathlib import Path

    return Path(daily_report_key(report_date))


def daily_model_report_path(report_date: str | date, slug: str):
    from pathlib import Path

    return Path(daily_model_report_key(report_date, slug))


def model_report_slug(model: dict) -> str:
    """Filesystem-safe slug for a model, e.g. 'grok-4.3' -> 'grok-4-3'."""
    raw = (model.get("model_name") or model.get("title") or model.get("id") or "model").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or "model"


def _normalize_identifier(identifier: str) -> str:
    return identifier.strip().lstrip("/")


async def list_reports(limit: int = 200) -> list[ReportMeta]:
    store = get_report_store()
    await store.ensure()
    entries: list[ReportMeta] = []
    for key in await store.list_keys():
        try:
            content = await store.read_text(key)
        except FileNotFoundError:
            continue
        meta = _build_meta_from_key(key, content=content)
        if meta is None:
            continue
        entries.append(meta)
        if len(entries) >= limit:
            break
    entries.sort(key=lambda item: (item.date, item.report_type), reverse=True)
    return entries[:limit]


async def resolve_report_key(identifier: str) -> str | None:
    store = get_report_store()
    await store.ensure()
    ident = _normalize_identifier(identifier)

    if await store.exists(ident):
        return ident

    if re.match(r"^\d{4}-\d{2}-\d{2}$", ident):
        suffix = f"{ident}-daily.md"
        for key in await store.list_keys():
            if key.endswith(suffix) and key.rsplit("/", 1)[-1] == suffix:
                return key
        return None

    if not ident.endswith(".md"):
        candidate = f"{ident}.md"
        if await store.exists(candidate):
            return candidate
    return None


async def read_report(identifier: str) -> tuple[str, str]:
    key = await resolve_report_key(identifier)
    if key is None:
        raise FileNotFoundError(f"Report not found: {identifier}")
    content = await get_report_store().read_text(key)
    return key, content


async def report_meta(identifier: str) -> ReportMeta | None:
    """Resolve a report and return its parsed metadata, or None if absent."""
    try:
        key, content = await read_report(identifier)
    except FileNotFoundError:
        return None
    return _build_meta_from_key(key, content=content)


async def write_daily_report(content: str, report_date: str | None = None) -> str:
    date_str = report_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = daily_report_key(date_str)
    await get_report_store().write_text(key, content)
    return key


async def write_model_daily_report(content: str, *, report_date: str, slug: str) -> str:
    key = daily_model_report_key(report_date, slug)
    await get_report_store().write_text(key, content)
    return key


async def write_report_key(key: str, content: str) -> str:
    await get_report_store().write_text(key, content)
    return key


async def load_daily_report_content(report_date: str | date) -> str | None:
    key = daily_report_key(report_date)
    store = get_report_store()
    if not await store.exists(key):
        return None
    return await store.read_text(key)


async def daily_report_exists(report_date: str | date) -> bool:
    return await get_report_store().exists(daily_report_key(report_date))


async def load_daily_reports_for_week(week_start: date) -> list[DailyReportEntry]:
    """Load Mon–Fri daily reports for the given week."""
    entries: list[DailyReportEntry] = []
    for offset in range(5):
        day = week_start + timedelta(days=offset)
        content = await load_daily_report_content(day)
        if content:
            entries.append(DailyReportEntry(date=day.isoformat(), content=content.strip()))
    return entries


async def load_weekend_daily_reports_for_week(week_start: date) -> list[DailyReportEntry]:
    """Load Sat/Sun dailies immediately before week_start (prior weekend)."""
    entries: list[DailyReportEntry] = []
    for offset in (-2, -1):
        day = week_start + timedelta(days=offset)
        content = await load_daily_report_content(day)
        if content:
            entries.append(DailyReportEntry(date=day.isoformat(), content=content.strip()))
    return entries


async def load_weekly_brief_for_week(week_start: date) -> str | None:
    key = weekly_brief_key(week_start)
    store = get_report_store()
    if not await store.exists(key):
        return None
    return (await store.read_text(key)).strip()


async def write_report_file(path_or_key, content: str) -> str:
    """Write report content. Accepts a key string or Path whose str is the key."""
    key = str(path_or_key).replace("\\", "/")
    # Strip accidental absolute prefixes if a Path was built from key only.
    if key.startswith("/"):
        # Prefer last two segments when an absolute path leaked in.
        parts = [p for p in key.split("/") if p]
        if len(parts) >= 2 and _WEEK_FOLDER_RE.match(parts[-2]):
            key = f"{parts[-2]}/{parts[-1]}"
        else:
            key = parts[-1]
    return await write_report_key(key, content)


async def delete_report(identifier: str) -> ReportMeta:
    """Delete a report and return its metadata."""
    meta = await report_meta(identifier)
    if meta is None:
        raise FileNotFoundError(f"Report not found: {identifier}")
    await get_report_store().delete(meta.filename)
    return meta


async def load_historical_weekly_debriefs(reference_date: str | date, max_weeks: int = 8) -> str:
    """Concatenate up to `max_weeks` recent AI weekly debriefs for LLM context."""
    current_week_start = resolve_weekly_target_date(reference_date)
    store = get_report_store()
    await store.ensure()
    candidates: list[tuple[date, str]] = []
    for key in await store.list_keys():
        name = key.rsplit("/", 1)[-1]
        parent = key.rsplit("/", 1)[0] if "/" in key else ""
        debrief_match = _WEEKLY_DEBRIEF_RE.match(name)
        folder_match = _WEEK_FOLDER_RE.match(parent) if parent else None
        if not debrief_match or not folder_match:
            continue
        week_start = date.fromisocalendar(int(folder_match.group(1)), int(folder_match.group(2)), 1)
        if week_start < current_week_start:
            candidates.append((week_start, key))
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = sorted(candidates[:max_weeks], key=lambda item: item[0])
    chunks: list[str] = []
    for _, key in selected:
        try:
            chunks.append((await store.read_text(key)).strip())
        except FileNotFoundError:
            continue
    return "\n\n---\n\n".join(chunk for chunk in chunks if chunk)


async def create_report_signed_url(identifier: str, *, expires_in: int = 3600) -> str | None:
    key = await resolve_report_key(identifier)
    if key is None:
        raise FileNotFoundError(f"Report not found: {identifier}")
    return await get_report_store().create_signed_url(key, expires_in=expires_in)
