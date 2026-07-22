"""HTTP routes for strategy backtest run history and control."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.backtesting.ai_feedback import begin_ai_feedback_job
from brokerai.backtesting.coordinator import get_backtest_coordinator
from brokerai.backtesting.periods import resolve_period_window
from brokerai.db.repositories.backtest_actions import BacktestActionsRepository
from brokerai.db.repositories.backtest_logs import BacktestLogsRepository
from brokerai.db.repositories.backtest_runs import (
    BACKTEST_PERIODS,
    BACKTEST_RUN_STATUS_COMPLETED,
    BACKTEST_RUN_STATUS_QUEUED,
    BACKTEST_RUN_STATUSES,
    BacktestRunsRepository,
    normalize_account_margin,
    normalize_backtest_period,
)
from brokerai.db.repositories.strategies import (
    BACKTEST_STATUS_RUNNING,
    StrategiesRepository,
)
from brokerai.trading.data.candle_cache import CandleCache, OANDA_SOURCE
from brokerai.web.routes.auth import require_auth
from brokerai.web.routes.market_data_helpers import (
    resolve_forex_pair,
    serialize_candle,
    validate_timeframe,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest-runs", tags=["backtest-runs"])

# Backtests span months of M15 bars; explore's 2000 cap is too small for review.
BACKTEST_CANDLE_LIMIT_MAX = 25_000


def _parse_candle_time_ms(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Cache stores nanosecond fractional seconds; fromisoformat accepts up to us.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "." in text:
        head, rest = text.split(".", 1)
        frac = ""
        tz = ""
        for index, char in enumerate(rest):
            if char.isdigit():
                frac += char
            else:
                tz = rest[index:]
                break
        text = f"{head}.{frac[:6]}{tz}"
    try:
        return datetime.fromisoformat(text).timestamp() * 1000.0
    except ValueError:
        return None


def slice_candles_around(
    candles: list[dict],
    *,
    around_iso: str,
    limit: int = BACKTEST_CANDLE_LIMIT_MAX,
) -> list[dict]:
    """Return up to ``limit`` candles centered on ``around_iso``.

    Edge cases:
    - Empty input → empty list.
    - Unparseable ``around_iso`` → last ``limit`` candles (same as default trim).
    - Anchor before/after the series → clamp to the nearer end.
    """
    if not candles or limit <= 0:
        return list(candles)
    if len(candles) <= limit:
        return list(candles)

    target_ms = _parse_candle_time_ms(around_iso)
    if target_ms is None:
        return candles[-limit:]

    best_idx = 0
    for index, candle in enumerate(candles):
        candle_ms = _parse_candle_time_ms(candle.get("time"))
        if candle_ms is None:
            continue
        if candle_ms <= target_ms:
            best_idx = index
        else:
            break

    half = limit // 2
    start = max(0, best_idx - half)
    end = min(len(candles), start + limit)
    start = max(0, end - limit)
    return candles[start:end]


class QueueBacktestRunsBody(BaseModel):
    strategy_ids: list[str] = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=120)
    instrument: str | None = Field(default=None, max_length=32)
    period: str = Field(default="6m", max_length=8)
    verbose: bool = False
    account_margin: float | None = None


@router.get("")
async def list_backtest_runs(
    _username: str = Depends(require_auth),
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None),
    strategy_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> JSONResponse:
    before_dt: datetime | None = None
    if before:
        try:
            before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            before_dt = None

    status_filter = status if status in BACKTEST_RUN_STATUSES else None
    repo = BacktestRunsRepository()
    runs = await repo.list_runs(
        strategy_id=strategy_id,
        status=status_filter,
        limit=limit,
        before=before_dt,
    )
    return JSONResponse({"runs": runs, "latest": runs[0] if runs else None})


@router.post("")
async def create_backtest_runs(
    body: QueueBacktestRunsBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    period_raw = (body.period or "6m").strip()
    if period_raw not in BACKTEST_PERIODS:
        raise HTTPException(status_code=400, detail="Invalid period")
    period = normalize_backtest_period(period_raw)
    ids = [sid.strip() for sid in body.strategy_ids if sid and sid.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="Select at least one strategy")

    strategies_repo = StrategiesRepository()
    strategies = await strategies_repo.queue_backtests(ids)
    if not strategies:
        raise HTTPException(status_code=404, detail="No matching strategies found")

    start, end = resolve_period_window(period)
    account_margin = normalize_account_margin(body.account_margin)
    runs = await BacktestRunsRepository().create_queued_runs(
        strategies,
        name=body.name,
        instrument=body.instrument,
        period=period,
        verbose=body.verbose,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        account_margin=account_margin,
    )
    return JSONResponse({"runs": runs, "queued": len(runs)})


@router.get("/{run_id}")
async def get_backtest_run(
    run_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = BacktestRunsRepository()
    run = await repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return JSONResponse(run)


@router.get("/{run_id}/candles")
async def get_backtest_run_candles(
    run_id: str,
    _username: str = Depends(require_auth),
    around: str | None = Query(
        default=None,
        description="ISO timestamp to center the returned window on when the "
        "full period exceeds the candle cap (action/trade chart snap).",
    ),
) -> JSONResponse:
    """Return cached OANDA candles covering a backtest run's evaluation window.

    Uses the Postgres candle cache directly (same data the worker used). Avoids
    the explore ``/api/market-data/candles`` 2000-bar cap, which truncates 6m
    M15 windows and left the review chart empty when focused near period end.

    When the period exceeds ``BACKTEST_CANDLE_LIMIT_MAX``, pass ``around`` to
    center the slice on an action/trade time instead of always returning the
    period tip.
    """
    run = await BacktestRunsRepository().get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")

    raw_symbol = str(run.get("instrument") or (run.get("instruments") or [None])[0] or "")
    if not raw_symbol.strip():
        raise HTTPException(status_code=400, detail="Backtest run has no instrument")
    pair = resolve_forex_pair(raw_symbol)
    timeframe = str(run.get("timeframe") or "M15")
    validate_timeframe(timeframe)

    since = run.get("period_start")
    until = run.get("period_end")
    if not since or not until:
        period = str(run.get("period") or "6m")
        start, end = resolve_period_window(period)
        since = start.isoformat()
        until = end.isoformat()

    cache = CandleCache()
    candles = await cache.read_candles(
        pair,
        timeframe,
        source=OANDA_SOURCE,
        since=str(since),
        until=str(until),
    )
    if not candles:
        # Best-effort backfill if the cache was pruned after the run completed.
        try:
            result = await cache.backfill(pair, timeframe, str(since), str(until))
            if result.error:
                logger.warning(
                    "Backtest run %s candle backfill warning: %s", run_id, result.error
                )
        except Exception:
            logger.exception("Backtest run %s candle backfill failed", run_id)
        candles = await cache.read_candles(
            pair,
            timeframe,
            source=OANDA_SOURCE,
            since=str(since),
            until=str(until),
        )

    if len(candles) > BACKTEST_CANDLE_LIMIT_MAX:
        if around and str(around).strip():
            candles = slice_candles_around(
                candles, around_iso=str(around).strip(), limit=BACKTEST_CANDLE_LIMIT_MAX
            )
        else:
            candles = candles[-BACKTEST_CANDLE_LIMIT_MAX:]

    if not candles:
        raise HTTPException(
            status_code=503,
            detail="Candle data unavailable for this backtest window.",
        )

    window_since = str(candles[0].get("time") or since)
    window_until = str(candles[-1].get("time") or until)

    return JSONResponse(
        {
            "symbol": pair,
            "timeframe": timeframe,
            "source": OANDA_SOURCE,
            "since": str(since),
            "until": str(until),
            "window_since": window_since,
            "window_until": window_until,
            "around": around,
            "candles": [serialize_candle(candle) for candle in candles],
        }
    )


@router.get("/{run_id}/logs")
async def list_backtest_logs(
    run_id: str,
    _username: str = Depends(require_auth),
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=500, ge=1, le=2000),
    level: str | None = Query(default=None),
) -> JSONResponse:
    if await BacktestRunsRepository().get_by_id(run_id) is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    logs = await BacktestLogsRepository().list_for_run(
        run_id, after_id=after_id, limit=limit, level=level
    )
    return JSONResponse({"logs": logs})


@router.get("/{run_id}/actions")
async def list_backtest_actions(
    run_id: str,
    _username: str = Depends(require_auth),
    after_sequence: int | None = Query(default=None, ge=0),
    kind: str | None = Query(default=None),
    limit: int = Query(default=2000, ge=1, le=10000),
) -> JSONResponse:
    if await BacktestRunsRepository().get_by_id(run_id) is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    actions = await BacktestActionsRepository().list_for_run(
        run_id, after_sequence=after_sequence, kind=kind, limit=limit
    )
    return JSONResponse({"actions": actions})


@router.post("/{run_id}/start")
async def start_backtest_run(
    run_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = BacktestRunsRepository()
    run = await repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    if run["status"] != BACKTEST_RUN_STATUS_QUEUED:
        raise HTTPException(status_code=400, detail=f"Cannot start run in status {run['status']}")
    updated = await repo.mark_running(run_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    strategy_id = str(updated.get("strategy_id") or "")
    if strategy_id:
        await StrategiesRepository().set_backtest_status(strategy_id, BACKTEST_STATUS_RUNNING)
    get_backtest_coordinator().notify_manual_start(run_id)
    return JSONResponse(updated)


@router.post("/{run_id}/ai-feedback")
async def request_backtest_ai_feedback(
    run_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    """Queue AI strategy feedback for a completed backtest (runs on the API loop)."""
    repo = BacktestRunsRepository()
    run = await repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    if run.get("status") != BACKTEST_RUN_STATUS_COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="AI feedback is only available for completed backtests",
        )
    try:
        updated = await begin_ai_feedback_job(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(updated, status_code=202)


@router.post("/{run_id}/cancel")
async def cancel_backtest_run(
    run_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = BacktestRunsRepository()
    updated = await repo.request_cancel(run_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return JSONResponse(updated)


@router.delete("/{run_id}")
async def delete_backtest_run(
    run_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = BacktestRunsRepository()
    run = await repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    if run["status"] == "running":
        await repo.request_cancel(run_id)
    await BacktestLogsRepository().delete_for_run(run_id)
    await BacktestActionsRepository().delete_for_run(run_id)
    deleted = await repo.delete_by_id(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return JSONResponse({"id": run_id, "status": "deleted"})
