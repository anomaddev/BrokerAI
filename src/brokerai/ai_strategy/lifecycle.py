"""AI Strategy execution-phase and warm-up lifecycle (strategy doc, not params)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

PHASE_WARMING = "warming"
PHASE_READY = "ready"
PHASE_LIVE = "live"
EXECUTION_PHASES = frozenset({PHASE_WARMING, PHASE_READY, PHASE_LIVE})

DEFAULT_WARMUP_TRADING_DAYS = 5
DEFAULT_MIN_CLOSED_BARS_PER_DAY = 1
AI_STRATEGY_PRESET_ID = "ai_strategy"


def is_ai_strategy_doc(strategy: dict[str, Any] | None) -> bool:
    if not strategy:
        return False
    return str(strategy.get("preset_id") or "") == AI_STRATEGY_PRESET_ID


def get_execution_phase(strategy: dict[str, Any] | None) -> str:
    if not strategy:
        return PHASE_LIVE
    raw = strategy.get("execution_phase")
    if isinstance(raw, str) and raw.strip() in EXECUTION_PHASES:
        return raw.strip()
    # Non-AI strategies are always live for dispatch.
    if not is_ai_strategy_doc(strategy):
        return PHASE_LIVE
    return PHASE_WARMING


def is_shadow_phase(phase: str) -> bool:
    return phase in {PHASE_WARMING, PHASE_READY}


def is_catchup_context(context: Any) -> bool:
    """True when pipeline is in catchup/bootstrap (no LLM / no warm-up advance)."""
    if context is None:
        return False
    if bool(getattr(context, "catchup", False)):
        return True
    if bool(getattr(context, "bootstrap", False)):
        return True
    return False


def default_warmup_doc(
    *,
    target_days: int | None = None,
    min_closed_bars_per_day: int = DEFAULT_MIN_CLOSED_BARS_PER_DAY,
    now: datetime | None = None,
) -> dict[str, Any]:
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "unit": "trading_days_et",
        "target_days": target_days,
        "min_closed_bars_per_day": max(1, int(min_closed_bars_per_day)),
        "episode_id": uuid4().hex,
        "started_at": stamp.isoformat(),
        "eligible_trading_days": [],
        "completed_days": 0,
        "bars_today_et": 0,
        "current_trading_day_et": None,
        "ready_at": None,
        "live_at": None,
    }


def normalize_lifecycle(doc: dict[str, Any]) -> dict[str, Any]:
    """Return sanitized execution_phase + warmup for AI strategies."""
    phase = get_execution_phase(doc)
    warmup_raw = doc.get("warmup") if isinstance(doc.get("warmup"), dict) else {}
    base = default_warmup_doc()
    if warmup_raw:
        try:
            target = warmup_raw.get("target_days", base["target_days"])
            target_days = None if target is None else max(1, int(target))
        except (TypeError, ValueError):
            target_days = base["target_days"]
        try:
            min_bars = max(1, int(warmup_raw.get("min_closed_bars_per_day", DEFAULT_MIN_CLOSED_BARS_PER_DAY)))
        except (TypeError, ValueError):
            min_bars = DEFAULT_MIN_CLOSED_BARS_PER_DAY
        eligible = warmup_raw.get("eligible_trading_days") or []
        if not isinstance(eligible, list):
            eligible = []
        base.update(
            {
                "unit": "trading_days_et",
                "target_days": target_days,
                "min_closed_bars_per_day": min_bars,
                "episode_id": str(warmup_raw.get("episode_id") or base["episode_id"]),
                "started_at": str(warmup_raw.get("started_at") or base["started_at"]),
                "eligible_trading_days": [str(d) for d in eligible if d],
                "completed_days": max(0, int(warmup_raw.get("completed_days") or 0)),
                "bars_today_et": max(0, int(warmup_raw.get("bars_today_et") or 0)),
                "current_trading_day_et": warmup_raw.get("current_trading_day_et"),
                "ready_at": warmup_raw.get("ready_at"),
                "live_at": warmup_raw.get("live_at"),
            }
        )
    return {"execution_phase": phase, "warmup": base}


def ensure_lifecycle_on_create(
    doc: dict[str, Any],
    *,
    default_warmup_trading_days: int = DEFAULT_WARMUP_TRADING_DAYS,
) -> dict[str, Any]:
    """Attach warming lifecycle when creating an AI Strategy."""
    if not is_ai_strategy_doc(doc):
        return doc
    out = dict(doc)
    out["execution_phase"] = PHASE_WARMING
    out["warmup"] = default_warmup_doc(target_days=None)
    out.setdefault("ai_improve", {"enabled": True, "last_queued_et_date": None, "skip_reason": None})
    # Store resolved default separately for UI when target_days is null.
    out["_warmup_default_days"] = max(1, int(default_warmup_trading_days))
    return out


def effective_warmup_target_days(strategy: dict[str, Any], global_default: int = DEFAULT_WARMUP_TRADING_DAYS) -> int:
    warmup = strategy.get("warmup") if isinstance(strategy.get("warmup"), dict) else {}
    raw = warmup.get("target_days")
    if raw is None:
        return max(1, int(global_default))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return max(1, int(global_default))


def trading_day_et(when: datetime | None = None) -> str:
    stamp = when or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(ET).date().isoformat()


def advance_warmup_on_realtime_bar(
    strategy: dict[str, Any],
    *,
    candle_time: datetime | None,
    catchup: bool,
    global_default_days: int = DEFAULT_WARMUP_TRADING_DAYS,
    forex_open: bool = True,
) -> dict[str, Any]:
    """
    Advance warm-up progress for a realtime closed bar.

    Counts an ET trading day only when forex is open and
    ``min_closed_bars_per_day`` bars have been seen that day.
    Catchup/bootstrap never advances progress.
    """
    if not is_ai_strategy_doc(strategy):
        return strategy
    phase = get_execution_phase(strategy)
    if phase not in {PHASE_WARMING}:
        return strategy
    if catchup or not forex_open or candle_time is None:
        return strategy

    lifecycle = normalize_lifecycle(strategy)
    warmup = dict(lifecycle["warmup"])
    day = trading_day_et(candle_time)
    current = warmup.get("current_trading_day_et")
    if current != day:
        warmup["current_trading_day_et"] = day
        warmup["bars_today_et"] = 1
    else:
        warmup["bars_today_et"] = int(warmup.get("bars_today_et") or 0) + 1

    min_bars = int(warmup.get("min_closed_bars_per_day") or DEFAULT_MIN_CLOSED_BARS_PER_DAY)
    eligible = list(warmup.get("eligible_trading_days") or [])
    if warmup["bars_today_et"] >= min_bars and day not in eligible:
        eligible.append(day)
        warmup["eligible_trading_days"] = eligible
        warmup["completed_days"] = len(eligible)

    target = effective_warmup_target_days(
        {"warmup": warmup},
        global_default=global_default_days,
    )
    out = dict(strategy)
    out["execution_phase"] = PHASE_WARMING
    out["warmup"] = warmup
    if int(warmup.get("completed_days") or 0) >= target:
        out["execution_phase"] = PHASE_READY
        warmup["ready_at"] = datetime.now(timezone.utc).isoformat()
        out["warmup"] = warmup
    return out


def promote_to_live(strategy: dict[str, Any]) -> dict[str, Any]:
    phase = get_execution_phase(strategy)
    if phase != PHASE_READY and phase != PHASE_LIVE:
        raise ValueError("Strategy must be ready before promoting to live")
    out = dict(strategy)
    lifecycle = normalize_lifecycle(out)
    warmup = dict(lifecycle["warmup"])
    warmup["live_at"] = datetime.now(timezone.utc).isoformat()
    out["execution_phase"] = PHASE_LIVE
    out["warmup"] = warmup
    return out


def reset_warmup_episode(
    strategy: dict[str, Any],
    *,
    default_warmup_trading_days: int = DEFAULT_WARMUP_TRADING_DAYS,
) -> dict[str, Any]:
    """New episode after disable/re-enable — never auto-jump to live."""
    out = dict(strategy)
    out["execution_phase"] = PHASE_WARMING
    out["warmup"] = default_warmup_doc(target_days=None)
    out["_warmup_default_days"] = max(1, int(default_warmup_trading_days))
    return out


def _parse_candle_time(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        stamp = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            stamp = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


async def advance_ai_strategy_warmups_for_bar(
    strategies: list[dict[str, Any]],
    *,
    candle_time: datetime | str | None,
    catchup: bool,
    forex_open: bool | None = None,
    global_default_days: int | None = None,
) -> int:
    """Advance warm-up on realtime bars for AI strategies in ``strategies``.

    Persists lifecycle via ``StrategiesRepository.save_lifecycle`` and mutates
    the in-memory strategy dicts so downstream Broker sees the updated phase.

    Returns the number of strategies whose lifecycle was persisted.
    """
    if catchup or not strategies:
        return 0

    stamp = _parse_candle_time(candle_time)
    if stamp is None:
        return 0

    from brokerai.trading.data.market_calendar import is_forex_open

    open_now = is_forex_open(stamp) if forex_open is None else bool(forex_open)
    default_days = DEFAULT_WARMUP_TRADING_DAYS
    if global_default_days is None:
        try:
            from brokerai.db.repositories.asset_settings import AssetSettingsRepository

            forex = await AssetSettingsRepository().get("forex")
            default_days = int(forex.get("default_warmup_trading_days") or DEFAULT_WARMUP_TRADING_DAYS)
        except Exception:
            default_days = DEFAULT_WARMUP_TRADING_DAYS
    else:
        default_days = max(1, int(global_default_days))

    from brokerai.db.repositories.strategies import StrategiesRepository

    repo = StrategiesRepository()
    advanced = 0
    for strategy in strategies:
        if not is_ai_strategy_doc(strategy):
            continue
        if get_execution_phase(strategy) != PHASE_WARMING:
            continue
        before_phase = get_execution_phase(strategy)
        before_days = int((strategy.get("warmup") or {}).get("completed_days") or 0)
        updated = advance_warmup_on_realtime_bar(
            strategy,
            candle_time=stamp,
            catchup=False,
            global_default_days=default_days,
            forex_open=open_now,
        )
        after_phase = get_execution_phase(updated)
        after_days = int((updated.get("warmup") or {}).get("completed_days") or 0)
        if after_phase == before_phase and after_days == before_days:
            # Still refresh bars_today / ticker fields when they moved.
            before_bars = int((strategy.get("warmup") or {}).get("bars_today_et") or 0)
            after_bars = int((updated.get("warmup") or {}).get("bars_today_et") or 0)
            if after_bars == before_bars:
                continue
        strategy_id = str(strategy.get("id") or "")
        if not strategy_id:
            continue
        saved = await repo.save_lifecycle(
            strategy_id,
            {
                "execution_phase": updated["execution_phase"],
                "warmup": updated["warmup"],
            },
        )
        if saved:
            strategy["execution_phase"] = saved.get("execution_phase", updated["execution_phase"])
            strategy["warmup"] = saved.get("warmup", updated["warmup"])
            advanced += 1
    return advanced
