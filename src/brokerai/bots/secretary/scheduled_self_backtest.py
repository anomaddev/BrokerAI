"""Secretary deferral helpers for daily AI Strategy self-backtests."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from brokerai.ai_strategy.daily_backtest import maybe_queue_daily_ai_strategy_backtests
from brokerai.ai_strategy.lifecycle import trading_day_et
from brokerai.db.repositories.backtest_settings import BacktestSettingsRepository

logger = logging.getLogger(__name__)

# After a successful probe, wait until the next ET day before re-checking.
_AFTER_PROBE = timedelta(minutes=30)

# Settings disabled: wait until fingerprint changes (secretary clears on change).
STABLE_UNTIL_SETTINGS = datetime(9999, 1, 1, tzinfo=timezone.utc)


def backtest_settings_fingerprint(settings: dict[str, Any]) -> str:
    return "|".join(
        [
            f"enabled={settings.get('daily_ai_strategy_backtest_enabled')!r}",
            f"period={settings.get('daily_ai_strategy_backtest_period')!r}",
        ]
    )


def next_daily_ai_backtest_probe_at(now: datetime, *, done_today: bool) -> datetime:
    """Defer until later today (retry) or several hours later when done."""
    _ = trading_day_et(now)
    if done_today:
        return now + timedelta(hours=6)
    return now + _AFTER_PROBE


async def maybe_run_daily_ai_strategy_backtests(
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Secretary entrypoint: load settings and queue eligible daily runs."""
    stamp = now or datetime.now(timezone.utc)
    settings = await BacktestSettingsRepository().get()
    if not settings.get("daily_ai_strategy_backtest_enabled"):
        return {"queued": [], "skipped": {}, "reason": "disabled"}
    summary = await maybe_queue_daily_ai_strategy_backtests(now=stamp, settings=settings)
    queued = summary.get("queued") or []
    if queued:
        logger.info(
            "Secretary — queued %d AI Strategy daily backtest(s) for %s",
            len(queued),
            summary.get("et_date"),
        )
    return summary
