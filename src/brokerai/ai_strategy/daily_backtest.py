"""Queue daily compiled-playbook backtests for AI Strategies.

Cadence is ET calendar day: ``cadence_key = f"{strategy_id}:{et_date}"``.
Skips when disabled, already queued today, digest missing/empty/unchanged,
or a prior daily run for the strategy is still queued/running.

Uses Slice 3 :class:`StrategyMemoryDigestsRepository` for digest reads.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from brokerai.ai_strategy.compile_playbook import compile_playbook_strategy_doc
from brokerai.ai_strategy.lifecycle import is_ai_strategy_doc, trading_day_et
from brokerai.ai_strategy.memory_digest import (
    digest_is_queueable,
    digest_version_key,
    normalize_memory_digest,
)
from brokerai.db.repositories.backtest_runs import (
    BACKTEST_RUN_STATUS_QUEUED,
    BACKTEST_RUN_STATUS_RUNNING,
    BacktestRunsRepository,
)
from brokerai.db.repositories.backtest_settings import BacktestSettingsRepository
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.db.repositories.strategy_learning import StrategyMemoryDigestsRepository

logger = logging.getLogger(__name__)

ORIGIN_AI_STRATEGY_DAILY = "ai_strategy_daily"


def daily_cadence_key(strategy_id: str, *, et_date: str | None = None) -> str:
    day = et_date or trading_day_et()
    return f"{strategy_id}:{day}"


def strategy_allows_daily_ai_backtest(strategy: dict[str, Any]) -> bool:
    """True when an enabled AI Strategy has learn + improve toggles on."""
    if not strategy or not strategy.get("enabled"):
        return False
    if not is_ai_strategy_doc(strategy):
        return False
    improve = strategy.get("ai_improve") if isinstance(strategy.get("ai_improve"), dict) else {}
    if improve.get("enabled") is False:
        return False
    params = strategy.get("params") if isinstance(strategy.get("params"), dict) else {}
    ai = params.get("ai") if isinstance(params.get("ai"), dict) else {}
    if not bool(ai.get("learn_enabled")):
        return False
    return True


def skip_reason_for_strategy(
    strategy: dict[str, Any],
    *,
    digest: dict[str, Any] | None,
    existing_cadence: dict[str, Any] | None,
    prior_daily_runs: list[dict[str, Any]],
    et_date: str,
) -> str | None:
    """Return a human skip reason, or ``None`` when the strategy should queue."""
    _ = et_date
    if not strategy_allows_daily_ai_backtest(strategy):
        return "learn_or_improve_disabled"
    if not digest_is_queueable(digest):
        return "no_digest"
    if existing_cadence is not None:
        return "already_queued_today"
    for prior in prior_daily_runs:
        status = str(prior.get("status") or "")
        if status in {BACKTEST_RUN_STATUS_QUEUED, BACKTEST_RUN_STATUS_RUNNING}:
            return "prior_still_running"
    digest_version = digest_version_key(normalize_memory_digest(digest))
    if digest_version:
        for prior in prior_daily_runs:
            if str(prior.get("digest_version") or "") == digest_version:
                return "digest_unchanged"
    return None


async def maybe_queue_daily_ai_strategy_backtests(
    *,
    now: datetime | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Idempotently queue compiled-playbook daily backtests.

    Returns a summary: ``{queued: [...], skipped: {strategy_id: reason}}``.
    """
    stamp = now or datetime.now(timezone.utc)
    et_date = trading_day_et(stamp)
    settings_doc = settings or await BacktestSettingsRepository().get()
    if not settings_doc.get("daily_ai_strategy_backtest_enabled"):
        return {"queued": [], "skipped": {}, "reason": "disabled", "et_date": et_date}

    period = str(settings_doc.get("daily_ai_strategy_backtest_period") or "6m")
    strategies = await StrategiesRepository().list_enabled()
    digests_repo = StrategyMemoryDigestsRepository()
    runs_repo = BacktestRunsRepository()

    queued: list[dict[str, Any]] = []
    skipped: dict[str, str] = {}

    for strategy in strategies:
        if not is_ai_strategy_doc(strategy):
            continue
        strategy_id = str(strategy.get("id") or "")
        if not strategy_id:
            continue

        cadence_key = daily_cadence_key(strategy_id, et_date=et_date)
        digest = await digests_repo.get_latest(strategy_id)
        existing = await runs_repo.find_by_cadence_key(cadence_key)
        prior = await runs_repo.list_by_origin_for_strategy(
            strategy_id,
            origin=ORIGIN_AI_STRATEGY_DAILY,
            limit=10,
        )
        reason = skip_reason_for_strategy(
            strategy,
            digest=digest,
            existing_cadence=existing,
            prior_daily_runs=prior,
            et_date=et_date,
        )
        if reason:
            skipped[strategy_id] = reason
            await StrategiesRepository().save_lifecycle(
                strategy_id,
                {
                    "ai_improve": {
                        **(strategy.get("ai_improve") or {"enabled": True}),
                        "last_queued_et_date": (strategy.get("ai_improve") or {}).get(
                            "last_queued_et_date"
                        ),
                        "skip_reason": reason,
                    }
                },
            )
            continue

        compiled = compile_playbook_strategy_doc(strategy, digest)
        if compiled is None:
            skipped[strategy_id] = "no_digest"
            continue

        digest_version = digest_version_key(normalize_memory_digest(digest))
        created = await runs_repo.create_queued_runs(
            [compiled],
            name=f"{strategy.get('name') or 'AI Strategy'} daily playbook ({et_date})",
            period=period,
            origin=ORIGIN_AI_STRATEGY_DAILY,
            cadence_key=cadence_key,
            digest_version=digest_version,
        )
        if not created:
            skipped[strategy_id] = "queue_failed"
            continue

        queued.extend(created)
        await StrategiesRepository().save_lifecycle(
            strategy_id,
            {
                "ai_improve": {
                    **(strategy.get("ai_improve") or {"enabled": True}),
                    "last_queued_et_date": et_date,
                    "skip_reason": None,
                }
            },
        )
        logger.info(
            "Queued AI Strategy daily backtest strategy=%s cadence=%s digest=%s run=%s",
            strategy_id,
            cadence_key,
            digest_version,
            created[0].get("id"),
        )

    return {"queued": queued, "skipped": skipped, "et_date": et_date}
