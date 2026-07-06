from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from brokerai.bots.researcher.concurrency import gather_limited
from brokerai.bots.researcher.llm import analyze_with_model
from brokerai.bots.researcher.prompts import (
    build_analysis_messages,
    group_forex_pairs,
)
from brokerai.bots.researcher.rss import fetch_rss_articles
from brokerai.bots.researcher.sources import ResolvedSources, fetch_group_articles
from brokerai.db.repositories.asset_settings import (
    ASSET_CLASSES,
    AssetSettingsRepository,
    enabled_forex_pairs,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int], None]

# Progress band for article search (see runner.run_daily_report).
SEARCH_PROGRESS_START = 5
SEARCH_PROGRESS_END = 50

ASSET_CLASS_LABELS: dict[str, str] = {
    "forex": "Forex",
    "metals": "Precious Metals",
    "stocks": "Stocks",
    "crypto": "Crypto",
    "futures": "Futures",
    "options": "Options",
}

# Asset classes with full daily-report research implemented.
IMPLEMENTED_ASSET_CLASSES = frozenset({"forex"})


@dataclass
class BrokerResearchTarget:
    asset_class: str
    label: str
    enabled: bool
    items: list[str]
    implemented: bool

    @property
    def runnable(self) -> bool:
        return self.enabled and self.implemented and bool(self.items)

    @property
    def enabled_without_targets(self) -> bool:
        return self.enabled and self.implemented and not self.items

    @property
    def enabled_unimplemented(self) -> bool:
        return self.enabled and not self.implemented


@dataclass
class BrokerSectionResult:
    sections: list[str] = field(default_factory=list)
    processed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class GroupArticles:
    primary: str
    pairs: list[str]
    articles: list[dict]
    note: str | None = None


async def load_broker_targets() -> list[BrokerResearchTarget]:
    repo = AssetSettingsRepository()
    targets: list[BrokerResearchTarget] = []
    for asset_class in ASSET_CLASSES:
        doc = await repo.get(asset_class)
        enabled = bool(doc.get("enabled"))
        if asset_class == "forex":
            raw_pairs = list(doc.get("enabled_pairs") or [])
            items = enabled_forex_pairs(raw_pairs)
        else:
            # Reserved for future symbol/ticker selection UI.
            items = list(doc.get("enabled_symbols") or [])
        targets.append(
            BrokerResearchTarget(
                asset_class=asset_class,
                label=ASSET_CLASS_LABELS.get(asset_class, asset_class.title()),
                enabled=enabled,
                items=items,
                implemented=asset_class in IMPLEMENTED_ASSET_CLASSES,
            )
        )
    return targets


def broker_research_skip_reason(targets: list[BrokerResearchTarget]) -> str | None:
    enabled = [target for target in targets if target.enabled]
    if not enabled:
        return (
            "No broker asset classes are enabled. "
            "Enable at least one under Settings → Broker to generate a daily report."
        )

    if any(target.runnable for target in targets):
        return None

    details: list[str] = []
    for target in enabled:
        if target.enabled_without_targets:
            item_label = "pairs" if target.asset_class == "forex" else "symbols"
            details.append(f"{target.label} is enabled but no {item_label} are selected")
        elif target.enabled_unimplemented:
            details.append(f"{target.label} is enabled (daily report research not yet implemented)")

    detail_text = "; ".join(details) if details else "no research targets are configured"
    return f"No research targets ready for daily reports: {detail_text}."


def pending_broker_notes(targets: list[BrokerResearchTarget]) -> list[str]:
    """Markdown notes for enabled brokers that were not processed in this run."""
    lines: list[str] = []
    for target in targets:
        if not target.enabled or target.runnable:
            continue
        if target.enabled_without_targets:
            item_label = "pairs" if target.asset_class == "forex" else "symbols"
            lines.extend(
                [
                    f"## {target.label}",
                    "",
                    f"_{target.label} is enabled but no {item_label} are selected yet._",
                    "",
                ]
            )
        elif target.enabled_unimplemented:
            lines.extend(
                [
                    f"## {target.label}",
                    "",
                    f"_{target.label} is enabled. Daily report research for {target.label.lower()} "
                    "is not yet implemented._",
                    "",
                ]
            )
    return lines


async def prefetch_forex_articles(
    target: BrokerResearchTarget,
    sources: ResolvedSources,
    *,
    page_size: int = 10,
    concurrency: int = 6,
    on_progress: ProgressCallback | None = None,
) -> dict[str, GroupArticles]:
    """Fetch and merge articles for every forex group once, shared across models."""
    groups = group_forex_pairs(target.items)
    group_items = list(groups.items())
    total = len(group_items)
    if total == 0:
        return {}

    prefetch_sources = sources
    if sources.rss_enabled and sources.rss_articles is None:
        rss_articles, rss_notes = await fetch_rss_articles(categories=sources.rss_categories)
        if rss_notes:
            logger.info("RSS prefetch: %s", "; ".join(rss_notes))
        prefetch_sources = ResolvedSources(
            newsapi_enabled=sources.newsapi_enabled,
            newsapi_key=sources.newsapi_key,
            rss_enabled=sources.rss_enabled,
            rss_categories=sources.rss_categories,
            web_search=sources.web_search,
            x_search=sources.x_search,
            rss_articles=rss_articles,
        )

    completed = 0
    progress_lock = asyncio.Lock()

    async def fetch_one(primary: str, group_pairs: list[str]) -> GroupArticles:
        nonlocal completed
        try:
            articles, notes = await fetch_group_articles(
                prefetch_sources, primary, group_pairs, page_size=page_size
            )
            if notes:
                logger.info("Forex %s sources: %s", primary, "; ".join(notes))
            return GroupArticles(
                primary=primary,
                pairs=group_pairs,
                articles=articles,
                note="; ".join(notes) if notes else None,
            )
        except Exception as exc:
            logger.warning("Forex %s article fetch failed: %s", primary, exc)
            return GroupArticles(
                primary=primary,
                pairs=group_pairs,
                articles=[],
                note=f"fetch failed: {exc}",
            )
        finally:
            async with progress_lock:
                completed += 1
                if on_progress is not None:
                    span = SEARCH_PROGRESS_END - SEARCH_PROGRESS_START
                    progress = SEARCH_PROGRESS_START + int(span * completed / total)
                    on_progress(
                        "search",
                        f"Searching groups… ({completed}/{total})",
                        progress,
                    )

    results = await gather_limited(
        [fetch_one(primary, pairs) for primary, pairs in group_items],
        limit=concurrency,
    )

    out: dict[str, GroupArticles] = {}
    for (primary, _), result in zip(group_items, results):
        if isinstance(result, BaseException):
            logger.warning("Forex %s article fetch failed: %s", primary, result)
            out[primary] = GroupArticles(
                primary=primary,
                pairs=groups[primary],
                articles=[],
                note=f"fetch failed: {result}",
            )
            continue
        out[primary] = result
    return out


async def _analyze_forex_group(
    primary: str,
    group: GroupArticles,
    *,
    model: dict,
    reasoning_effort: str | None = None,
    historical_context: str | None = None,
    market_closed: bool = False,
) -> tuple[str, str | None, str | None]:
    """Return (primary, analysis_markdown, error_message)."""
    model_title = model.get("title") or model.get("model_name") or "Model"
    if not group.articles:
        return primary, None, f"Forex {primary}: {group.note or 'no articles found'}"

    messages = build_analysis_messages(
        primary,
        group.pairs,
        group.articles,
        historical_context=historical_context,
        market_closed=market_closed,
    )
    try:
        analysis = await analyze_with_model(
            model["type"],
            model["base_url"],
            model["model_name"],
            messages,
            model.get("api_key") or None,
            reasoning_effort=reasoning_effort,
            cost_context={
                "operation": "forex_analysis",
                "source": "daily_report",
                "forex_group": primary,
                "model_id": model.get("id"),
            },
        )
    except Exception as exc:
        logger.exception(
            "Forex research failed for group %s with model %s", primary, model_title
        )
        return primary, None, f"Forex {primary} ({model_title}): {exc}"

    return primary, analysis, None


async def run_forex_for_model(
    group_articles: dict[str, GroupArticles],
    *,
    model: dict,
    reasoning_effort: str | None = None,
    historical_context: str | None = None,
    market_closed: bool = False,
    concurrency: int = 4,
    on_progress: ProgressCallback | None = None,
) -> BrokerSectionResult:
    """Produce a single model's full forex analysis from prefetched articles."""
    result = BrokerSectionResult()
    result.sections.append("## Forex")
    result.sections.append("")

    group_order = list(group_articles.keys())
    total = len(group_order)
    if total == 0:
        return result

    completed = 0
    progress_lock = asyncio.Lock()

    async def analyze_one(primary: str) -> tuple[str, str | None, str | None]:
        nonlocal completed
        try:
            return await _analyze_forex_group(
                primary,
                group_articles[primary],
                model=model,
                reasoning_effort=reasoning_effort,
                historical_context=historical_context,
                market_closed=market_closed,
            )
        finally:
            async with progress_lock:
                completed += 1
                if on_progress is not None:
                    on_progress(
                        "model",
                        f"Analyzing {primary} group ({completed}/{total})…",
                        0,
                    )

    analysis_results = await gather_limited(
        [analyze_one(primary) for primary in group_order],
        limit=concurrency,
    )

    for primary, analysis_result in zip(group_order, analysis_results):
        if isinstance(analysis_result, BaseException):
            logger.exception("Forex research failed for group %s", primary)
            result.errors.append(f"Forex {primary}: {analysis_result}")
            continue

        _, analysis, error = analysis_result
        if error:
            result.errors.append(error)
            continue

        group = group_articles[primary]
        group_key = f"forex:{primary}"
        result.sections.append(f"### {primary} Group ({', '.join(group.pairs)})")
        result.sections.append("")
        result.sections.append(analysis or "")
        result.sections.append("")
        result.processed.append(group_key)

    return result


def non_forex_pending_sections(targets: list[BrokerResearchTarget]) -> list[str]:
    """Notes for enabled asset classes that are not produced by the forex pipeline."""
    lines: list[str] = []
    for target in targets:
        if not target.enabled:
            continue
        if target.asset_class == "forex":
            if not target.runnable:
                lines.extend(pending_broker_notes([target]))
            continue
        if target.asset_class not in IMPLEMENTED_ASSET_CLASSES:
            lines.extend(_unimplemented_section(target).sections)
    return lines


def _unimplemented_section(target: BrokerResearchTarget) -> BrokerSectionResult:
    if not target.enabled:
        return BrokerSectionResult()
    if target.items:
        return BrokerSectionResult(
            sections=[
                f"## {target.label}",
                "",
                f"_{target.label} symbols are configured but daily report research is not yet implemented._",
                "",
            ],
            errors=[f"{target.label}: research not yet implemented"],
        )
    return BrokerSectionResult(
        sections=[
            f"## {target.label}",
            "",
            f"_{target.label} is enabled. Daily report research is not yet implemented._",
            "",
        ],
    )


def broker_status_summary(targets: list[BrokerResearchTarget]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for target in targets:
        summary[target.asset_class] = {
            "label": target.label,
            "enabled": target.enabled,
            "implemented": target.implemented,
            "item_count": len(target.items),
            "runnable": target.runnable,
        }
    return summary
