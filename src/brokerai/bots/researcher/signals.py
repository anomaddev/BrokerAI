from __future__ import annotations

import re
from dataclasses import dataclass

from brokerai.bots.researcher.brokers import load_broker_targets
from brokerai.bots.researcher.reports import list_reports, read_report

_PAIR_HEADING_RE = re.compile(r"(?m)^####\s+([A-Z]{3}/[A-Z]{3})\s*$")
_FIELD_RE_TEMPLATE = r"(?mi)^\s*-\s*\*\*{label}\*\*\s*[—:-]\s*(.+)$"

_SIGNAL_VALUES = ("buy", "sell", "hold", "mixed")
_TONE_VALUES = ("bullish", "bearish", "neutral")
_CONVICTION_VALUES = ("low", "medium", "high")


@dataclass
class ForexPairSignal:
    signal: str | None = None
    tone: str | None = None
    approach: str | None = None
    conviction: str | None = None


def _match_first(value: str, allowed: tuple[str, ...]) -> str | None:
    lowered = value.lower()
    for candidate in allowed:
        if candidate in lowered:
            return candidate
    return None


def _extract_field(block: str, label: str) -> str | None:
    match = re.search(_FIELD_RE_TEMPLATE.format(label=re.escape(label)), block)
    if not match:
        return None
    return match.group(1).strip() or None


def parse_forex_signals(content: str) -> dict[str, ForexPairSignal]:
    """Parse per-pair signals from a synthesized daily report's Pair guidance blocks."""
    signals: dict[str, ForexPairSignal] = {}
    matches = list(_PAIR_HEADING_RE.finditer(content))
    for index, match in enumerate(matches):
        pair = match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        block = content[start:end]

        signal_raw = _extract_field(block, "Signal")
        tone_raw = _extract_field(block, "Tone")
        approach_raw = _extract_field(block, "Approach")
        conviction_raw = _extract_field(block, "Conviction")

        signals[pair] = ForexPairSignal(
            signal=_match_first(signal_raw, _SIGNAL_VALUES) if signal_raw else None,
            tone=_match_first(tone_raw, _TONE_VALUES) if tone_raw else None,
            approach=approach_raw,
            conviction=_match_first(conviction_raw, _CONVICTION_VALUES)
            if conviction_raw
            else None,
        )
    return signals


def _latest_daily_report():
    for meta in list_reports(limit=200):
        if meta.report_type == "daily":
            return meta
    return None


SIGNALS_CACHE_CATEGORY = "signals-snapshot"


async def compute_signals_snapshot() -> dict:
    """Build signals snapshot from the latest daily report on disk."""
    targets = [target for target in await load_broker_targets() if target.enabled]

    meta = _latest_daily_report()
    forex_signals: dict[str, ForexPairSignal] = {}
    if meta is not None:
        try:
            _, content = read_report(meta.filename)
        except FileNotFoundError:
            meta = None
        else:
            forex_signals = parse_forex_signals(content)

    asset_classes: list[dict] = []
    for target in targets:
        items: list[dict] = []
        if target.implemented and target.asset_class == "forex":
            for symbol in target.items:
                parsed = forex_signals.get(symbol)
                if parsed is None:
                    items.append(
                        {
                            "symbol": symbol,
                            "signal": None,
                            "tone": None,
                            "approach": None,
                            "conviction": None,
                            "status": "missing",
                        }
                    )
                else:
                    items.append(
                        {
                            "symbol": symbol,
                            "signal": parsed.signal,
                            "tone": parsed.tone,
                            "approach": parsed.approach,
                            "conviction": parsed.conviction,
                            "status": "ok",
                        }
                    )

        asset_classes.append(
            {
                "asset_class": target.asset_class,
                "label": target.label,
                "implemented": target.implemented,
                "items": items,
            }
        )

    return {
        "report_date": meta.date if meta else None,
        "report_filename": meta.filename if meta else None,
        "generated_at": meta.generated_at if meta else None,
        "asset_classes": asset_classes,
    }


async def build_signals_snapshot() -> dict:
    """Return cached snapshot when available, otherwise compute from disk."""
    from brokerai.db.repositories.research_cache import ResearchCacheRepository

    cache_repo = ResearchCacheRepository()
    cached = await cache_repo.find_latest_by_category(SIGNALS_CACHE_CATEGORY)
    payload = cached.get("payload") if cached else None
    if isinstance(payload, dict) and payload.get("asset_classes") is not None:
        return payload
    return await compute_signals_snapshot()


async def cache_signals_snapshot(snapshot: dict) -> None:
    report_date = snapshot.get("report_date")
    if not report_date:
        return
    from brokerai.db.repositories.research_cache import ResearchCacheRepository

    cache_repo = ResearchCacheRepository()
    await cache_repo.upsert(
        date=str(report_date),
        category=SIGNALS_CACHE_CATEGORY,
        summary="",
        payload=snapshot,
    )
