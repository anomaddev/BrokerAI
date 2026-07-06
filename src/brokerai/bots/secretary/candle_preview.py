from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from brokerai.bots.data_manager.candle_schedule import next_candle_close_at
from brokerai.bots.data_manager.forex_strategies import load_runnable_forex_strategies
from brokerai.config.settings import get_settings
from brokerai.strategies.params.constants import TIMEFRAMES
from brokerai.trading.work_plan import build_work_plan

logger = logging.getLogger(__name__)

_PREVIEW_CACHE: dict[str, Any] | None = None
_PREVIEW_CACHE_AT: datetime | None = None
_CACHE_TTL = timedelta(seconds=60)

_ASSET_SECTION_LABELS: dict[str, str] = {
    "forex": "Forex",
    "metals": "Precious Metals",
    "stocks": "Stocks",
    "options": "Options",
    "futures": "Futures",
    "crypto": "Crypto",
}
_ASSET_SECTION_ORDER: tuple[str, ...] = (
    "forex",
    "metals",
    "stocks",
    "options",
    "futures",
    "crypto",
)


def _parse_fetch_time(iso: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_target_timeframe(
    next_candle_fetches: dict[str, str] | None,
    *,
    now: datetime,
    work_plan_timeframes: tuple[str, ...],
) -> str | None:
    """Pick the earliest upcoming candle close timeframe (mirrors frontend logic)."""
    now_ms = int(now.timestamp() * 1000)
    best_timeframe: str | None = None
    best_target_at = float("inf")

    if next_candle_fetches:
        for timeframe, iso in next_candle_fetches.items():
            if timeframe not in TIMEFRAMES:
                continue
            parsed = _parse_fetch_time(iso)
            if parsed is None:
                continue
            target_ms = int(parsed.timestamp() * 1000)
            if target_ms <= now_ms:
                target_ms = int(next_candle_close_at(now, timeframe).timestamp() * 1000)
            if target_ms < best_target_at:
                best_target_at = target_ms
                best_timeframe = timeframe

    if best_timeframe:
        return best_timeframe

    if work_plan_timeframes:
        return work_plan_timeframes[0]

    for timeframe in get_settings().candle_default_timeframes.split(","):
        tf = timeframe.strip()
        if tf in TIMEFRAMES:
            return tf

    return None


def _target_at_for_timeframe(
    timeframe: str,
    *,
    now: datetime,
    next_candle_fetches: dict[str, str] | None,
) -> datetime:
    if next_candle_fetches and timeframe in next_candle_fetches:
        parsed = _parse_fetch_time(next_candle_fetches[timeframe])
        if parsed is not None and parsed > now:
            return parsed
    return next_candle_close_at(now, timeframe)


def _asset_section_label(asset_class: str) -> str:
    return _ASSET_SECTION_LABELS.get(
        asset_class,
        asset_class.replace("_", " ").title(),
    )


def _asset_section_sort_key(asset_class: str) -> tuple[int, str]:
    try:
        return (_ASSET_SECTION_ORDER.index(asset_class), asset_class)
    except ValueError:
        return (len(_ASSET_SECTION_ORDER), asset_class)


def _build_asset_sections(
    work_plan,
    timeframe: str,
) -> list[dict[str, Any]]:
    """Group symbols for the target timeframe by asset class."""
    by_asset: dict[str, set[str]] = {}
    for unit in work_plan.units:
        if unit.timeframe != timeframe:
            continue
        by_asset.setdefault(unit.asset_class, set()).add(unit.pair)

    sections: list[dict[str, Any]] = []
    for asset_class in sorted(by_asset.keys(), key=_asset_section_sort_key):
        symbols = sorted(by_asset[asset_class])
        if not symbols:
            continue
        sections.append(
            {
                "asset_class": asset_class,
                "label": _asset_section_label(asset_class),
                "symbols": symbols,
            }
        )
    return sections


async def preview_next_candle_watch(
    *,
    next_candle_fetches: dict[str, str] | None = None,
    now: datetime | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Return symbols the secretary will analyze on the next candle close.

    Results are cached for ~60s to avoid repeated MongoDB reads on dashboard polls.

    Edge cases:
    - No runnable strategies → ``symbols`` is empty with ``skip_reason`` when known.
    - ``next_candle_fetches`` from heartbeat aligns timeframe with the live secretary
      timeline when the orchestrator is running.
    """
    global _PREVIEW_CACHE, _PREVIEW_CACHE_AT

    when = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)

    if (
        not force_refresh
        and _PREVIEW_CACHE is not None
        and _PREVIEW_CACHE_AT is not None
        and when - _PREVIEW_CACHE_AT < _CACHE_TTL
    ):
        return dict(_PREVIEW_CACHE)

    result = await load_runnable_forex_strategies()
    work_plan = build_work_plan(result.strategies, asset_class="forex") if result.strategies else None
    work_plan_timeframes = work_plan.timeframes if work_plan else ()

    timeframe = _resolve_target_timeframe(
        next_candle_fetches,
        now=when,
        work_plan_timeframes=work_plan_timeframes,
    )

    if timeframe is None:
        payload: dict[str, Any] = {
            "timeframe": None,
            "target_at": None,
            "symbols": [],
            "asset_sections": [],
            "skip_reason": result.skip_reason or "no candle timeframe available",
        }
        _PREVIEW_CACHE = payload
        _PREVIEW_CACHE_AT = when
        return dict(payload)

    asset_sections: list[dict[str, Any]] = []
    symbols: list[str] = []
    if work_plan is not None:
        asset_sections = _build_asset_sections(work_plan, timeframe)
        symbols = sorted({symbol for section in asset_sections for symbol in section["symbols"]})

    target_at = _target_at_for_timeframe(timeframe, now=when, next_candle_fetches=next_candle_fetches)

    payload = {
        "timeframe": timeframe,
        "target_at": target_at.isoformat(),
        "symbols": symbols,
        "asset_sections": asset_sections,
        "skip_reason": result.skip_reason,
    }
    _PREVIEW_CACHE = payload
    _PREVIEW_CACHE_AT = when
    return dict(payload)


def clear_candle_preview_cache() -> None:
    """Reset preview cache (used in tests)."""
    global _PREVIEW_CACHE, _PREVIEW_CACHE_AT
    _PREVIEW_CACHE = None
    _PREVIEW_CACHE_AT = None
