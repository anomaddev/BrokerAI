from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from brokerai.bots.researcher.brokers import (
    BrokerResearchTarget,
    broker_research_skip_reason,
    broker_status_summary,
    load_broker_targets,
    non_forex_pending_sections,
    prefetch_forex_articles,
    run_forex_for_model,
)
from brokerai.bots.researcher.llm import analyze_with_model, test_model
from brokerai.bots.researcher.news import test_newsapi
from brokerai.bots.researcher.prompts import build_synthesis_messages, group_forex_pairs, is_market_closed
from brokerai.bots.researcher.reports import (
    delete_report,
    list_reports,
    load_historical_weekly_debriefs,
    model_report_slug,
    read_report,
    report_meta,
    reports_dir,
    write_daily_report,
    write_model_daily_report,
)
from brokerai.bots.researcher.sources import resolve_sources
from brokerai.config.settings import get_settings
from brokerai.db.repositories.ai_models import AiModelsRepository
from brokerai.db.repositories.data_connections import DataConnectionsRepository
from brokerai.db.repositories.research_cache import ResearchCacheRepository
from brokerai.db.repositories.research_settings import ResearchSettingsRepository
from brokerai.research_markets import describe_close_schedule, describe_schedule

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int], None]


def _emit_progress(
    on_progress: ProgressCallback | None,
    step: str,
    message: str,
    progress: int,
) -> None:
    if on_progress is not None:
        on_progress(step, message, progress)


@dataclass
class RunResult:
    ok: bool
    report_path: str | None = None
    model_report_paths: list[str] = field(default_factory=list)
    groups_processed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped_reason: str | None = None


def _skipped_ok(reason: str) -> RunResult:
    """Benign skip — not an error; no report is produced."""
    return RunResult(ok=True, skipped_reason=reason)


def _resolve_contributors(
    settings: dict, models_by_id: dict[str, dict]
) -> list[tuple[dict, dict]]:
    """Return (contributor_config, model_doc) for each enabled, available contributor."""
    resolved: list[tuple[dict, dict]] = []
    for entry in settings.get("contributor_models") or []:
        if not entry.get("enabled"):
            continue
        model = models_by_id.get(entry.get("model_id"))
        if model and model.get("enabled"):
            resolved.append((entry, model))
    return resolved


def _resolve_synthesis(
    settings: dict,
    models_by_id: dict[str, dict],
    contributors: list[tuple[dict, dict]],
) -> tuple[dict | None, str | None]:
    """Resolve the synthesis model. Returns (model_or_none, skip_reason_or_none)."""
    synthesis_id = settings.get("synthesis_model_id")
    if synthesis_id:
        model = models_by_id.get(synthesis_id)
        if not model:
            return None, "Synthesis model no longer exists; pick one in Settings → Daily Reports"
        if not model.get("enabled"):
            return None, f"Synthesis model '{model.get('title')}' is disabled"
        return model, None

    if len(contributors) <= 1:
        return None, None

    return None, (
        "Select a synthesis model in Settings → Daily Reports to merge multiple analysis models"
    )


def _needs_synthesis_llm(
    *,
    contributor_reports: list[dict[str, str]],
    contributors: list[tuple[dict, dict]],
    synthesis_model: dict | None,
) -> bool:
    """Return True when a separate LLM synthesis pass is required.

    Skips redundant second calls when one model already produced the only analysis,
    unless a different synthesis model is configured to re-process that output.
    """
    if synthesis_model is None:
        return False

    if len(contributor_reports) <= 1:
        if len(contributors) == 1:
            sole_contributor = contributors[0][1]
            return sole_contributor.get("id") != synthesis_model.get("id")
        # Multiple contributors configured but only one produced output — nothing to merge.
        return False

    return True


def _skip_per_model_daily_report(
    contributors: list[tuple[dict, dict]],
    synthesis_model: dict | None,
) -> bool:
    """Skip the per-model file when one contributor also serves as synthesis."""
    if len(contributors) != 1:
        return False
    if synthesis_model is None:
        return True
    sole_contributor = contributors[0][1]
    return sole_contributor.get("id") == synthesis_model.get("id")


def _model_label(model: dict) -> str:
    return model.get("title") or model.get("model_name") or model.get("id") or "Model"


async def get_research_status() -> dict:
    news_repo = DataConnectionsRepository()
    settings_repo = ResearchSettingsRepository()
    models_repo = AiModelsRepository()

    news = await news_repo.get_newsapi()
    settings = await settings_repo.get()
    all_models = await models_repo.list_all()
    models_by_id = {m["id"]: m for m in all_models}
    capabilities_map = await news_repo.get_model_capabilities_map()

    contributors = _resolve_contributors(settings, models_by_id)
    synthesis_model, _ = _resolve_synthesis(settings, models_by_id, contributors)
    if synthesis_model is None and len(contributors) == 1:
        synthesis_model = contributors[0][1]

    sources = resolve_sources(
        data_sources=settings.get("data_sources") or {},
        newsapi_doc=news,
        capabilities_map=capabilities_map,
        models_by_id=models_by_id,
    )

    broker_targets = await load_broker_targets()
    brokers = broker_status_summary(broker_targets)
    forex = brokers.get("forex", {})

    return {
        "newsapi_enabled": bool(news.get("enabled") and news.get("api_key")),
        "newsapi_configured": bool(news.get("api_key")),
        "contributor_titles": [_model_label(model) for _, model in contributors],
        "contributor_count": len(contributors),
        "synthesis_model_title": _model_label(synthesis_model) if synthesis_model else None,
        "data_sources_active": sources.describe(),
        "brokers": brokers,
        "forex_enabled": bool(forex.get("enabled")),
        "forex_pairs_count": int(forex.get("item_count") or 0),
        "last_daily_run_date": settings.get("last_daily_run_date"),
        "daily_report_enabled": settings.get("daily_report_enabled", False),
        "daily_report_market_id": settings.get("daily_report_market_id"),
        "daily_report_market_offset_hours": settings.get("daily_report_market_offset_hours"),
        "schedule_description": describe_schedule(
            settings.get("daily_report_market_id", "london"),
            settings.get("daily_report_market_offset_hours", -2),
        ),
        "weekly_brief_enabled": settings.get("weekly_brief_enabled", False),
        "weekly_debrief_enabled": settings.get("weekly_debrief_enabled", False),
        "last_weekly_brief_run_week": settings.get("last_weekly_brief_run_week"),
        "last_weekly_debrief_run_week": settings.get("last_weekly_debrief_run_week"),
        "weekly_brief_schedule_description": describe_schedule(
            settings.get("weekly_brief_market_id", "london"),
            settings.get("weekly_brief_market_offset_hours", -1),
        ),
        "weekly_debrief_schedule_description": describe_close_schedule(
            settings.get("weekly_debrief_market_id", "london"),
            settings.get("weekly_debrief_market_offset_hours", 1),
        ),
        "reports_dir": str(reports_dir()),
        "report_count": len(list_reports(limit=100)),
    }


async def test_news_connection() -> tuple[bool, str]:
    news = await DataConnectionsRepository().get_newsapi()
    if not news.get("api_key"):
        return False, "NewsAPI key is not configured"
    return await test_newsapi(news["api_key"])


async def test_model_connection() -> tuple[bool, str]:
    settings = await ResearchSettingsRepository().get()
    models_repo = AiModelsRepository()
    all_models = await models_repo.list_all()
    models_by_id = {m["id"]: m for m in all_models}

    contributors = _resolve_contributors(settings, models_by_id)
    if not contributors:
        return False, "No research models selected in Settings → Daily Reports"

    results: list[str] = []
    all_ok = True
    for _, model in contributors:
        ok, message = await test_model(
            model["type"],
            model["base_url"],
            model["model_name"],
            model.get("api_key") or None,
        )
        results.append(f"{_model_label(model)}: {message}")
        if not ok:
            all_ok = False

    return all_ok, "; ".join(results)


def _report_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _model_report_header(report_date: str, model: dict, reasoning_effort: str) -> list[str]:
    return [
        f"# Daily Research Report ({_model_label(model)}) — {report_date}",
        "",
        f"Generated at {_report_timestamp()}",
        f"Model: {_model_label(model)} ({model.get('model_name')})",
        f"Reasoning effort: {reasoning_effort}",
        "",
    ]


def _final_report_header(
    report_date: str,
    synthesis_model: dict | None,
    contributor_titles: list[str],
    synthesis_reasoning: str,
) -> list[str]:
    lines = [
        f"# Daily Research Report — {report_date}",
        "",
        f"Generated at {_report_timestamp()}",
    ]
    if synthesis_model is not None:
        lines.append(
            f"Synthesis model: {_model_label(synthesis_model)} "
            f"({synthesis_model.get('model_name')}) · reasoning {synthesis_reasoning}"
        )
    elif len(contributor_titles) == 1:
        lines.append(f"Model: {contributor_titles[0]}")
    lines.append(f"Contributing models: {', '.join(contributor_titles) or '—'}")
    lines.append("")
    return lines


async def run_daily_report(
    *,
    force: bool = False,
    manual: bool = False,
    on_progress: ProgressCallback | None = None,
) -> RunResult:
    today_date = datetime.now(timezone.utc).date()
    today = today_date.isoformat()
    settings_repo = ResearchSettingsRepository()
    settings = await settings_repo.get()

    if not manual and not settings.get("daily_report_enabled", False):
        return RunResult(ok=False, skipped_reason="Daily reports are disabled")

    if not force and settings.get("last_daily_run_date") == today:
        return RunResult(ok=False, skipped_reason=f"Daily report already ran for {today}")

    models_repo = AiModelsRepository()
    connections_repo = DataConnectionsRepository()
    all_models = await models_repo.list_all()
    models_by_id = {m["id"]: m for m in all_models}

    contributors = _resolve_contributors(settings, models_by_id)
    if not contributors:
        return RunResult(ok=False, skipped_reason="No enabled analysis models selected")

    synthesis_model, synth_skip = _resolve_synthesis(settings, models_by_id, contributors)
    if synth_skip:
        return RunResult(ok=False, skipped_reason=synth_skip)

    news = await connections_repo.get_newsapi()
    capabilities_map = await connections_repo.get_model_capabilities_map()
    sources = resolve_sources(
        data_sources=settings.get("data_sources") or {},
        newsapi_doc=news,
        capabilities_map=capabilities_map,
        models_by_id=models_by_id,
    )
    if not sources.any_active:
        return RunResult(
            ok=False,
            skipped_reason="No data sources enabled (NewsAPI, web search, or X search)",
        )

    broker_targets = await load_broker_targets()
    broker_skip = broker_research_skip_reason(broker_targets)
    if broker_skip:
        logger.info("Daily report skipped: %s", broker_skip)
        return _skipped_ok(broker_skip)

    forex_target = _runnable_forex_target(broker_targets)
    historical_context = load_historical_weekly_debriefs(today_date, max_weeks=8)
    market_closed = is_market_closed(today_date)
    pending_sections = non_forex_pending_sections(broker_targets)

    logger.info("Daily report data sources: %s", ", ".join(sources.describe()) or "none")

    app_settings = get_settings()
    search_concurrency = app_settings.research_search_concurrency
    analysis_concurrency = app_settings.research_analysis_concurrency
    group_count = len(group_forex_pairs(forex_target.items)) if forex_target else 0

    logger.info(
        "Daily report search batch: %d groups, concurrency=%d, sources=[%s]",
        group_count,
        search_concurrency,
        ", ".join(sources.describe()) or "none",
    )

    _emit_progress(on_progress, "prefetch", "Preparing forex pair searches…", 5)
    group_articles = (
        await prefetch_forex_articles(
            forex_target,
            sources,
            on_progress=on_progress,
            concurrency=search_concurrency,
        )
        if forex_target
        else {}
    )

    errors: list[str] = []
    processed: set[str] = set()
    contributor_reports: list[dict[str, str]] = []
    model_report_paths: list[str] = []
    skip_per_model_report = _skip_per_model_daily_report(contributors, synthesis_model)

    contributor_count = len(contributors)
    analysis_group_count = max(len(group_articles), 1)
    for index, (entry, model) in enumerate(contributors):
        model_label = _model_label(model)
        logger.info(
            "Daily report analysis batch: model=%s, %d groups, concurrency=%d",
            model_label,
            len(group_articles),
            analysis_concurrency,
        )
        model_progress_start = 50 + int(35 * index / max(contributor_count, 1))
        model_progress_end = 50 + int(35 * (index + 1) / max(contributor_count, 1))

        def model_group_progress(
            _step: str,
            message: str,
            _progress: int,
            *,
            _start: int = model_progress_start,
            _end: int = model_progress_end,
            _label: str = model_label,
        ) -> None:
            match = re.search(r"\((\d+)/(\d+)\)", message)
            completed_groups = int(match.group(1)) if match else 0
            span = max(_end - _start, 1)
            progress = _start + int(span * completed_groups / analysis_group_count)
            _emit_progress(on_progress, "model", f"{_label}: {message}", progress)

        reasoning = entry.get("reasoning_effort")
        section = await run_forex_for_model(
            group_articles,
            model=model,
            reasoning_effort=reasoning,
            historical_context=historical_context,
            market_closed=market_closed,
            concurrency=analysis_concurrency,
            on_progress=model_group_progress if on_progress else None,
        )
        errors.extend(section.errors)
        processed.update(section.processed)

        if not section.processed:
            logger.warning("Model %s produced no usable sections", _model_label(model))
            continue

        contributor_reports.append(
            {"model": _model_label(model), "content": "\n".join(section.sections).strip()}
        )

        if skip_per_model_report:
            logger.info(
                "Skipping per-model daily file: %s is the sole analysis and synthesis model",
                _model_label(model),
            )
            continue

        body_lines = (
            _model_report_header(today, model, reasoning or "default")
            + section.sections
            + pending_sections
        )
        path = write_model_daily_report(
            "\n".join(body_lines).strip(),
            report_date=today,
            slug=model_report_slug(model),
        )
        model_report_paths.append(str(path))

    if not contributor_reports:
        return RunResult(
            ok=False,
            errors=errors,
            skipped_reason="No analysis models produced a report",
        )

    synthesis_reasoning = settings.get("synthesis_reasoning_effort") or "high"
    run_synthesis = _needs_synthesis_llm(
        contributor_reports=contributor_reports,
        contributors=contributors,
        synthesis_model=synthesis_model,
    )
    if run_synthesis:
        _emit_progress(on_progress, "synthesis", "Synthesizing report…", 85)
    if not run_synthesis and synthesis_model is not None:
        if len(contributors) == 1:
            logger.info(
                "Skipping synthesis: %s is the only analysis model and already produced the report",
                _model_label(contributors[0][1]),
            )
        else:
            logger.info(
                "Skipping synthesis: only one of %d analysis models produced a report",
                len(contributors),
            )

    final_forex, synth_error = await _build_final_forex(
        contributor_reports,
        synthesis_model=synthesis_model if run_synthesis else None,
        synthesis_reasoning=synthesis_reasoning,
        report_date=today,
        historical_context=historical_context,
        market_closed=market_closed,
    )
    if synth_error:
        errors.append(synth_error)

    header = _final_report_header(
        today,
        synthesis_model if run_synthesis else None,
        [report["model"] for report in contributor_reports],
        synthesis_reasoning,
    )
    final_sections = [*header, final_forex, "", *pending_sections]

    _emit_progress(on_progress, "write", "Saving report…", 95)
    report_path = write_daily_report("\n".join(final_sections).strip(), report_date=today)
    await settings_repo.set_last_daily_run_date(today)

    cache_repo = ResearchCacheRepository()
    await cache_repo.upsert(
        date=today,
        category="forex-synthesis",
        summary=final_forex[:2000],
        sources=[],
    )

    from brokerai.bots.researcher.signals import cache_signals_snapshot, compute_signals_snapshot

    signals_snapshot = await compute_signals_snapshot()
    await cache_signals_snapshot(signals_snapshot)

    _emit_progress(on_progress, "done", "Complete", 100)
    return RunResult(
        ok=True,
        report_path=str(report_path),
        model_report_paths=model_report_paths,
        groups_processed=sorted(processed),
        errors=errors,
    )


def _runnable_forex_target(targets: list[BrokerResearchTarget]) -> BrokerResearchTarget | None:
    for target in targets:
        if target.asset_class == "forex" and target.runnable:
            return target
    return None


async def _build_final_forex(
    contributor_reports: list[dict[str, str]],
    *,
    synthesis_model: dict | None,
    synthesis_reasoning: str,
    report_date: str,
    historical_context: str | None,
    market_closed: bool,
) -> tuple[str, str | None]:
    """Return (final_forex_markdown, error_or_none)."""
    if synthesis_model is None:
        return contributor_reports[0]["content"], None

    messages = build_synthesis_messages(
        contributor_reports,
        report_date=report_date,
        historical_context=historical_context,
        market_closed=market_closed,
    )
    try:
        synthesized = await analyze_with_model(
            synthesis_model["type"],
            synthesis_model["base_url"],
            synthesis_model["model_name"],
            messages,
            synthesis_model.get("api_key") or None,
            reasoning_effort=synthesis_reasoning,
        )
        return synthesized, None
    except Exception as exc:
        logger.exception("Synthesis failed with model %s", _model_label(synthesis_model))
        fallback = contributor_reports[0]
        note = (
            f"_Synthesis model failed ({exc}); showing {fallback['model']} analysis._\n\n"
            + fallback["content"]
        )
        return note, f"Synthesis ({_model_label(synthesis_model)}): {exc}"


def list_report_entries(limit: int = 200) -> list[dict]:
    return [
        {
            "filename": r.filename,
            "date": r.date,
            "type": r.report_type,
            "path": r.path,
            "model_label": r.model_label,
            "generated_at": r.generated_at,
            "reasoning_effort": r.reasoning_effort,
            "size_bytes": r.size_bytes,
        }
        for r in list_reports(limit=limit)
    ]


async def delete_report_entry(identifier: str) -> dict:
    """Delete a report and apply related cleanup for synthesized daily reports."""
    meta = report_meta(identifier)
    if meta is None:
        raise FileNotFoundError(f"Report not found: {identifier}")

    if meta.report_type == "daily":
        settings_repo = ResearchSettingsRepository()
        settings = await settings_repo.get()
        if settings.get("last_daily_run_date") == meta.date:
            await settings_repo.clear_last_daily_run_date()
        cache_repo = ResearchCacheRepository()
        await cache_repo.delete_one(meta.date, "forex-synthesis")
        await cache_repo.delete_one(meta.date, "signals-snapshot")

    deleted = delete_report(identifier)
    return {
        "filename": deleted.filename,
        "date": deleted.date,
        "type": deleted.report_type,
    }


def run_daily_report_result_payload(result: RunResult) -> dict:
    return {
        "ok": result.ok,
        "report_path": result.report_path,
        "model_report_paths": result.model_report_paths,
        "groups_processed": result.groups_processed,
        "errors": result.errors,
        "skipped_reason": result.skipped_reason,
    }


async def get_signals_snapshot() -> dict:
    from brokerai.bots.researcher.signals import build_signals_snapshot

    return await build_signals_snapshot()


def read_report_content(identifier: str) -> dict:
    filename, content = read_report(identifier)
    meta = report_meta(identifier)
    return {
        "filename": filename,
        "content": content,
        "date": meta.date if meta else None,
        "type": meta.report_type if meta else None,
        "model_label": meta.model_label if meta else None,
        "generated_at": meta.generated_at if meta else None,
        "reasoning_effort": meta.reasoning_effort if meta else None,
    }
