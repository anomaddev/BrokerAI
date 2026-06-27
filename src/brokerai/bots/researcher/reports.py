from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from itertools import islice
from pathlib import Path

from brokerai.config.settings import get_settings


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

_legacy_migrated = False


def _strip_model_name(value: str) -> str:
    """Drop the trailing technical model name, e.g. 'Grok 4.3 (grok-4.3)' -> 'Grok 4.3'."""
    return _MODEL_NAME_SUFFIX_RE.sub("", value).strip()


def _model_label_from_filename(name: str) -> str | None:
    match = _DAILY_MODEL_SLUG_RE.search(name)
    if not match:
        return None
    return match.group(1).replace("-", " ")


def _parse_report_header(path: Path) -> dict[str, str | None]:
    """Extract display metadata from the first lines of a report file.

    Reads only the leading lines so listing many reports stays cheap.
    """
    info: dict[str, str | None] = {
        "model_label": None,
        "generated_at": None,
        "reasoning_effort": None,
    }
    try:
        with path.open("r", encoding="utf-8") as fh:
            head = list(islice(fh, 15))
    except OSError:
        return info

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


def _build_meta(
    path: Path, filename: str, report_date: str, report_type: str
) -> ReportMeta:
    header = _parse_report_header(path)
    model_label = header.get("model_label")
    if not model_label and report_type == "daily_model":
        model_label = _model_label_from_filename(path.name)
    try:
        size_bytes = path.stat().st_size
    except OSError:
        size_bytes = 0
    return ReportMeta(
        filename=filename,
        date=report_date,
        report_type=report_type,
        path=str(path),
        model_label=model_label,
        generated_at=header.get("generated_at"),
        reasoning_effort=header.get("reasoning_effort"),
        size_bytes=size_bytes,
    )


def reports_dir() -> Path:
    path = get_settings().data_dir / "research" / "reports"
    path.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_reports(path)
    return path


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


def week_dir_for_date(d: str | date, *, create: bool = False) -> Path:
    iso_year, iso_week = week_folder_key(d)
    path = reports_dir() / f"{iso_year}_{iso_week}"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def week_start_from_folder_name(folder_name: str) -> date | None:
    match = _WEEK_FOLDER_RE.match(folder_name)
    if not match:
        return None
    return date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)


@dataclass
class DailyReportEntry:
    date: str
    content: str


def weekly_brief_path(week_start: date) -> Path:
    iso_year, iso_week, _ = week_start.isocalendar()
    week_dir = reports_dir() / f"{iso_year}_{iso_week}"
    week_dir.mkdir(parents=True, exist_ok=True)
    return week_dir / f"weekly_brief_{iso_week}.md"


def weekly_debrief_path(week_start: date) -> Path:
    iso_year, iso_week, _ = week_start.isocalendar()
    week_dir = reports_dir() / f"{iso_year}_{iso_week}"
    week_dir.mkdir(parents=True, exist_ok=True)
    return week_dir / f"weekly_debrief_{iso_week}.md"


def daily_report_path(report_date: str | date) -> Path:
    d = _as_date(report_date)
    return week_dir_for_date(d, create=True) / f"{d.isoformat()}-daily.md"


def model_report_slug(model: dict) -> str:
    """Filesystem-safe slug for a model, e.g. 'grok-4.3' -> 'grok-4-3'."""
    raw = (model.get("model_name") or model.get("title") or model.get("id") or "model").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or "model"


def daily_model_report_path(report_date: str | date, slug: str) -> Path:
    d = _as_date(report_date)
    return week_dir_for_date(d, create=True) / f"{d.isoformat()}-daily_{slug}.md"


def _meta_from_path(path: Path, root: Path) -> ReportMeta | None:
    name = path.name
    daily_match = _FILENAME_RE.match(name)
    if daily_match and daily_match.group(2) == "daily":
        rel = path.relative_to(root)
        return _build_meta(path, str(rel), daily_match.group(1), "daily")

    if daily_match and daily_match.group(2).startswith("daily_"):
        rel = path.relative_to(root)
        return _build_meta(path, str(rel), daily_match.group(1), "daily_model")

    weekly_brief_match = _WEEKLY_BRIEF_RE.match(name)
    if weekly_brief_match and path.parent != root:
        folder_match = _WEEK_FOLDER_RE.match(path.parent.name)
        if folder_match:
            week_start = date.fromisocalendar(int(folder_match.group(1)), int(folder_match.group(2)), 1)
            rel = path.relative_to(root)
            return _build_meta(path, str(rel), week_start.isoformat(), "weekly_brief")

    weekly_debrief_match = _WEEKLY_DEBRIEF_RE.match(name)
    if weekly_debrief_match and path.parent != root:
        folder_match = _WEEK_FOLDER_RE.match(path.parent.name)
        if folder_match:
            week_start = date.fromisocalendar(int(folder_match.group(1)), int(folder_match.group(2)), 1)
            rel = path.relative_to(root)
            return _build_meta(path, str(rel), week_start.isoformat(), "weekly_debrief")

    if daily_match:
        return _build_meta(path, name, daily_match.group(1), daily_match.group(2))
    return None


def _iter_report_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*.md"):
        if path.is_file():
            paths.append(path)
    return paths


def list_reports(limit: int = 200) -> list[ReportMeta]:
    directory = reports_dir()
    entries: list[ReportMeta] = []
    for path in sorted(_iter_report_paths(directory), key=lambda p: str(p), reverse=True):
        meta = _meta_from_path(path, directory)
        if meta is None:
            continue
        entries.append(meta)
        if len(entries) >= limit:
            break
    entries.sort(key=lambda item: (item.date, item.report_type), reverse=True)
    return entries[:limit]


def resolve_report_path(identifier: str) -> Path | None:
    directory = reports_dir()
    ident = identifier.strip()

    if "/" in ident or ident.endswith(".md"):
        candidate = directory / ident
        if candidate.is_file():
            return candidate

    if re.match(r"^\d{4}-\d{2}-\d{2}$", ident):
        matches = sorted(directory.glob(f"**/{ident}-daily.md"), reverse=True)
        if matches:
            return matches[0]
        legacy = sorted(directory.glob(f"{ident}-*.md"), reverse=True)
        return legacy[0] if legacy else None

    candidate = directory / f"{ident}.md"
    if candidate.is_file():
        return candidate
    candidate = directory / ident
    return candidate if candidate.is_file() else None


def _resolve_within_reports(identifier: str) -> Path:
    directory = reports_dir()
    path = resolve_report_path(identifier)
    if path is None:
        raise FileNotFoundError(f"Report not found: {identifier}")
    resolved = path.resolve()
    if not resolved.is_relative_to(directory.resolve()):
        raise FileNotFoundError(f"Report not found: {identifier}")
    return resolved


def read_report(identifier: str) -> tuple[str, str]:
    path = _resolve_within_reports(identifier)
    try:
        filename = str(path.relative_to(reports_dir().resolve()))
    except ValueError:
        filename = path.name
    return filename, path.read_text(encoding="utf-8")


def report_meta(identifier: str) -> ReportMeta | None:
    """Resolve a report and return its parsed metadata, or None if absent."""
    try:
        path = _resolve_within_reports(identifier)
    except FileNotFoundError:
        return None
    return _meta_from_path(path, reports_dir().resolve())


def write_daily_report(content: str, report_date: str | None = None) -> Path:
    date_str = report_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = daily_report_path(date_str)
    path.write_text(content, encoding="utf-8")
    return path


def write_model_daily_report(content: str, *, report_date: str, slug: str) -> Path:
    path = daily_model_report_path(report_date, slug)
    path.write_text(content, encoding="utf-8")
    return path


def load_daily_report_content(report_date: str | date) -> str | None:
    path = daily_report_path(report_date)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def daily_report_exists(report_date: str | date) -> bool:
    return daily_report_path(report_date).is_file()


def load_daily_reports_for_week(week_start: date) -> list[DailyReportEntry]:
    """Load Mon–Fri daily reports for the given week."""
    entries: list[DailyReportEntry] = []
    for offset in range(5):
        day = week_start + timedelta(days=offset)
        content = load_daily_report_content(day)
        if content:
            entries.append(DailyReportEntry(date=day.isoformat(), content=content.strip()))
    return entries


def load_weekend_daily_reports_for_week(week_start: date) -> list[DailyReportEntry]:
    """Load Sat/Sun dailies immediately before week_start (prior weekend)."""
    entries: list[DailyReportEntry] = []
    for offset in (-2, -1):
        day = week_start + timedelta(days=offset)
        content = load_daily_report_content(day)
        if content:
            entries.append(DailyReportEntry(date=day.isoformat(), content=content.strip()))
    return entries


def load_weekly_brief_for_week(week_start: date) -> str | None:
    path = weekly_brief_path(week_start)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip()


def write_report_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def delete_report(identifier: str) -> ReportMeta:
    """Delete a report file and return its metadata."""
    path = _resolve_within_reports(identifier)
    meta = _meta_from_path(path, reports_dir().resolve())
    if meta is None:
        raise FileNotFoundError(f"Report not found: {identifier}")
    path.unlink(missing_ok=True)
    return meta


def _weekly_debrief_path_candidates(directory: Path) -> list[tuple[date, Path]]:
    candidates: list[tuple[date, Path]] = []

    for week_dir in directory.iterdir():
        if not week_dir.is_dir():
            continue
        week_start = week_start_from_folder_name(week_dir.name)
        if week_start is None:
            continue
        iso_week = week_start.isocalendar()[1]
        debrief_path = week_dir / f"weekly_debrief_{iso_week}.md"
        if debrief_path.is_file():
            candidates.append((week_start, debrief_path))

    return candidates


def load_historical_weekly_debriefs(reference_date: str | date, max_weeks: int = 8) -> str:
    """Concatenate up to `max_weeks` recent AI weekly debriefs for LLM context."""
    current_week_start = resolve_weekly_target_date(reference_date)
    directory = reports_dir()

    candidates = [
        (week_start, path)
        for week_start, path in _weekly_debrief_path_candidates(directory)
        if week_start < current_week_start
    ]
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = sorted(candidates[:max_weeks], key=lambda item: item[0])

    chunks = [path.read_text(encoding="utf-8").strip() for _, path in selected]
    return "\n\n---\n\n".join(chunk for chunk in chunks if chunk)


def _migrate_legacy_reports(directory: Path) -> None:
    global _legacy_migrated
    if _legacy_migrated:
        return
    _legacy_migrated = True

    for path in list(directory.glob("*.md")):
        if not path.is_file():
            continue

        daily_match = _FILENAME_RE.match(path.name)
        if daily_match and daily_match.group(2) == "daily":
            report_date = daily_match.group(1)
            dest = daily_report_path(report_date)
            if dest != path and not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(dest))
