from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from brokerai.bots.researcher.brokers import (
    broker_research_skip_reason,
    load_broker_targets,
    prefetch_forex_articles,
)
from brokerai.bots.researcher.llm import analyze_with_model
from brokerai.bots.researcher.prompts import (
    build_weekly_brief_messages,
    build_weekly_debrief_messages,
)
from brokerai.bots.researcher.reports import (
    daily_report_exists,
    load_daily_report_content,
    load_daily_reports_for_week,
    load_historical_weekly_debriefs,
    load_weekend_daily_reports_for_week,
    load_weekly_brief_for_week,
    resolve_weekly_target_date,
    weekly_brief_path,
    weekly_debrief_path,
    write_report_file,
)
from brokerai.bots.researcher.sources import resolve_sources
from brokerai.db.repositories.ai_models import AiModelsRepository
from brokerai.db.repositories.data_connections import DataConnectionsRepository
from brokerai.db.repositories.research_settings import ResearchSettingsRepository
from brokerai.research_markets import (
    detect_schedule_conflict,
    iso_week_key,
    is_past_weekly_brief_run,
    is_past_weekly_debrief_run,
    should_defer_weekly_brief_for_daily,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int], None]

MIN_WEEKDAY_DAILIES_FOR_DEBRIEF = 1


def _emit_progress(
    on_progress: ProgressCallback | None,
    step: str,
    message: str,
    progress: int,
) -> None:
    if on_progress is not None:
        on_progress(step, message, progress)


@dataclass
class WeeklyRunResult:
    ok: bool
    report_path: str | None = None
    week_key: str | None = None
    errors: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


def _model_label(model: dict) -> str:
    return model.get("title") or model.get("model_name") or model.get("id") or "Model"


def _report_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _weekly_header(
    title: str,
    week_start: date,
    model: dict,
    reasoning_effort: str,
) -> list[str]:
    return [
        f"# {title} — Week of {week_start.isoformat()}",
        "",
        f"Generated at {_report_timestamp()}",
        f"Model: {_model_label(model)} ({model.get('model_name')})",
        f"Reasoning effort: {reasoning_effort}",
        "",
    ]


def _target_week_for_brief(now: datetime) -> tuple[date, str]:
    week_start = resolve_weekly_target_date(now.date())
    return week_start, iso_week_key(week_start)


def _completed_debrief_week(now: datetime, settings: dict) -> tuple[date, str] | None:
    """Return the most recent week whose Friday close schedule has passed."""
    market_id = settings.get("weekly_debrief_market_id", "london")
    offset = settings.get("weekly_debrief_market_offset_hours", 1)
    today = now.date()
    current_monday = today - timedelta(days=today.weekday())

    for weeks_back in range(5):
        week_start = current_monday - timedelta(days=7 * weeks_back)
        if is_past_weekly_debrief_run(now, week_start, market_id, offset):
            return week_start, iso_week_key(week_start)
    return None


async def _resolve_weekly_model(settings: dict, key: str) -> tuple[dict | None, str | None]:
    model_id = settings.get(key)
    if not model_id:
        return None, f"No model selected for {key}"

    models_repo = AiModelsRepository()
    model = await models_repo.find_by_id(str(model_id))
    if not model:
        return None, f"Model no longer exists: {model_id}"
    if not model.get("enabled"):
        return None, f"Model is disabled: {_model_label(model)}"
    return model, None


def _daily_dicts(entries: list) -> list[dict[str, str]]:
    return [{"date": entry.date, "content": entry.content} for entry in entries]


async def run_weekly_brief(
    *,
    force: bool = False,
    manual: bool = False,
    on_progress: ProgressCallback | None = None,
) -> WeeklyRunResult:
    now = datetime.now(timezone.utc)
    settings_repo = ResearchSettingsRepository()
    settings = await settings_repo.get()

    if not manual and not settings.get("weekly_brief_enabled", False):
        return WeeklyRunResult(ok=False, skipped_reason="Weekly brief is disabled")

    week_start, week_key = _target_week_for_brief(now)
    if not force and settings.get("last_weekly_brief_run_week") == week_key:
        return WeeklyRunResult(ok=False, skipped_reason=f"Weekly brief already ran for {week_key}")

    model, model_skip = await _resolve_weekly_model(settings, "weekly_brief_model_id")
    if model_skip:
        return WeeklyRunResult(ok=False, skipped_reason=model_skip)

    today = now.date().isoformat()
    daily_completed = (
        settings.get("last_daily_run_date") == today or daily_report_exists(today)
    )
    if not manual:
        if should_defer_weekly_brief_for_daily(
            now,
            daily_report_enabled=bool(settings.get("daily_report_enabled", False)),
            daily_market_id=settings.get("daily_report_market_id", "london"),
            daily_offset_hours=settings.get("daily_report_market_offset_hours", -2),
            brief_market_id=settings.get("weekly_brief_market_id", "london"),
            brief_offset_hours=settings.get("weekly_brief_market_offset_hours", -1),
            daily_completed_today=daily_completed,
        ):
            return WeeklyRunResult(
                ok=False,
                skipped_reason=f"Daily report for {today} is not ready yet",
            )
        if not daily_completed:
            return WeeklyRunResult(
                ok=False,
                skipped_reason=f"Daily report for {today} is not ready yet",
            )

    open_day = week_start.isoformat()
    open_daily = load_daily_report_content(open_day)
    if not open_daily:
        return WeeklyRunResult(
            ok=False,
            skipped_reason=f"Open-day daily report missing for {open_day}",
        )

    _emit_progress(on_progress, "load", "Loading daily reports…", 15)
    weekend_dailies = load_weekend_daily_reports_for_week(week_start)
    dailies = _daily_dicts(weekend_dailies)
    dailies.append({"date": open_day, "content": open_daily.strip()})

    conflict = detect_schedule_conflict(
        daily_market_id=settings.get("daily_report_market_id", "london"),
        daily_offset_hours=settings.get("daily_report_market_offset_hours", -2),
        brief_market_id=settings.get("weekly_brief_market_id", "london"),
        brief_offset_hours=settings.get("weekly_brief_market_offset_hours", -1),
        on=now.date(),
    )
    if conflict:
        logger.warning("Weekly brief schedule conflict: %s", conflict)

    articles: list[dict] = []
    broker_targets = await load_broker_targets()
    broker_skip = broker_research_skip_reason(broker_targets)
    if not broker_skip:
        _emit_progress(on_progress, "prefetch", "Loading market articles…", 25)
        from brokerai.bots.researcher.runner import _runnable_forex_target

        forex_target = _runnable_forex_target(broker_targets)
        if forex_target:
            models_repo = AiModelsRepository()
            connections_repo = DataConnectionsRepository()
            all_models = await models_repo.list_all()
            models_by_id = {m["id"]: m for m in all_models}
            news = await connections_repo.get_newsapi()
            capabilities_map = await connections_repo.get_model_capabilities_map()
            sources = resolve_sources(
                data_sources=settings.get("data_sources") or {},
                newsapi_doc=news,
                capabilities_map=capabilities_map,
                models_by_id=models_by_id,
            )
            if sources.any_active:
                group_articles = await prefetch_forex_articles(forex_target, sources)
                for group in group_articles.values():
                    articles.extend(group)

    reasoning = settings.get("weekly_brief_reasoning_effort") or "high"
    messages = build_weekly_brief_messages(
        week_start=week_start,
        dailies=dailies,
        articles=articles or None,
    )

    assert model is not None
    _emit_progress(on_progress, "llm", "Generating weekly brief…", 50)
    try:
        body = await analyze_with_model(
            model["type"],
            model["base_url"],
            model["model_name"],
            messages,
            model.get("api_key") or None,
            reasoning_effort=reasoning,
        )
    except Exception as exc:
        logger.exception("Weekly brief failed")
        return WeeklyRunResult(ok=False, errors=[str(exc)])

    header = _weekly_header("Weekly Research Brief", week_start, model, reasoning)
    path = weekly_brief_path(week_start)
    _emit_progress(on_progress, "write", "Saving report…", 95)
    write_report_file(path, "\n".join([*header, body.strip()]).strip())
    await settings_repo.set_last_weekly_brief_run_week(week_key)

    _emit_progress(on_progress, "done", "Complete", 100)
    return WeeklyRunResult(ok=True, report_path=str(path), week_key=week_key)


async def run_weekly_debrief(
    *,
    force: bool = False,
    manual: bool = False,
    on_progress: ProgressCallback | None = None,
) -> WeeklyRunResult:
    now = datetime.now(timezone.utc)
    settings_repo = ResearchSettingsRepository()
    settings = await settings_repo.get()

    if not manual and not settings.get("weekly_debrief_enabled", False):
        return WeeklyRunResult(ok=False, skipped_reason="Weekly debrief is disabled")

    target = _completed_debrief_week(now, settings)
    if target is None:
        return WeeklyRunResult(
            ok=False,
            skipped_reason="Weekly debrief schedule has not passed for a completed week",
        )

    week_start, week_key = target
    if not force and settings.get("last_weekly_debrief_run_week") == week_key:
        return WeeklyRunResult(ok=False, skipped_reason=f"Weekly debrief already ran for {week_key}")

    model, model_skip = await _resolve_weekly_model(settings, "weekly_debrief_model_id")
    if model_skip:
        return WeeklyRunResult(ok=False, skipped_reason=model_skip)

    _emit_progress(on_progress, "load", "Loading week context…", 15)
    weekday_dailies = load_daily_reports_for_week(week_start)
    if len(weekday_dailies) < MIN_WEEKDAY_DAILIES_FOR_DEBRIEF:
        return WeeklyRunResult(
            ok=False,
            skipped_reason=f"Insufficient weekday dailies for week {week_key}",
        )

    missing_dates: list[str] = []
    for offset in range(5):
        day = week_start + timedelta(days=offset)
        if not daily_report_exists(day):
            missing_dates.append(day.isoformat())

    weekly_brief = load_weekly_brief_for_week(week_start)
    historical = load_historical_weekly_debriefs(week_start, max_weeks=4)

    reasoning = settings.get("weekly_debrief_reasoning_effort") or "high"
    messages = build_weekly_debrief_messages(
        week_start=week_start,
        dailies=_daily_dicts(weekday_dailies),
        weekly_brief=weekly_brief,
        historical_debriefs=historical or None,
        missing_dates=missing_dates or None,
    )

    assert model is not None
    _emit_progress(on_progress, "llm", "Generating weekly debrief…", 50)
    try:
        body = await analyze_with_model(
            model["type"],
            model["base_url"],
            model["model_name"],
            messages,
            model.get("api_key") or None,
            reasoning_effort=reasoning,
        )
    except Exception as exc:
        logger.exception("Weekly debrief failed")
        return WeeklyRunResult(ok=False, errors=[str(exc)])

    header = _weekly_header("Weekly Research Debrief", week_start, model, reasoning)
    path = weekly_debrief_path(week_start)
    _emit_progress(on_progress, "write", "Saving report…", 95)
    write_report_file(path, "\n".join([*header, body.strip()]).strip())
    await settings_repo.set_last_weekly_debrief_run_week(week_key)

    _emit_progress(on_progress, "done", "Complete", 100)
    return WeeklyRunResult(ok=True, report_path=str(path), week_key=week_key)


def weekly_run_result_payload(result: WeeklyRunResult) -> dict:
    return {
        "ok": result.ok,
        "report_path": result.report_path,
        "week_key": result.week_key,
        "errors": result.errors,
        "skipped_reason": result.skipped_reason,
    }
