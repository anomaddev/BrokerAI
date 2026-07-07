from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.bots.data_manager.candle_requirements import strategy_params
from brokerai.bots.data_manager.candle_schedule import timeframe_to_duration
from brokerai.bots.data_manager.service import require_data_manager_service
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.db.repositories.strategy_analysis_runs import StrategyAnalysisRunsRepository
from brokerai.strategies.candles import compute_required_candles, effective_min_candles
from brokerai.trading.data.candle_cache import OANDA_SOURCE
from brokerai.trading.manual_analysis import run_manual_strategy_analysis
from brokerai.web.routes.auth import require_auth
from brokerai.web.routes.market_data_helpers import serialize_candle, validate_timeframe

router = APIRouter(prefix="/api/strategy-analysis-runs", tags=["strategy-analysis-runs"])
logger = logging.getLogger(__name__)


class RunManualAnalysisBody(BaseModel):
    strategy_id: str = Field(..., min_length=1)
    asset_class: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)

# Bars shown before/after the analyzed candle in the detail chart.
ANALYSIS_DISPLAY_BARS_BEFORE = 40
ANALYSIS_DISPLAY_BARS_AFTER = 5


def _parse_instant(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _candle_open_time(candle: dict[str, Any]) -> datetime | None:
    return _parse_instant(candle.get("time"))


def _bars_since_anchor(anchor: datetime, *, now: datetime, bar_duration) -> int:
    """Closed bars from ``anchor`` open through the latest bar at ``now``."""
    anchor_utc = anchor.astimezone(timezone.utc) if anchor.tzinfo else anchor.replace(tzinfo=timezone.utc)
    now_utc = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if now_utc <= anchor_utc:
        return 1
    elapsed = now_utc - anchor_utc
    return max(1, int(elapsed / bar_duration) + 1)


def _analysis_signal_anchor_time(
    run: dict[str, Any],
    *,
    bar_duration: timedelta | None = None,
) -> datetime | None:
    """Return the bar open time to center the analysis chart."""
    metadata = run.get("metadata") or {}
    if metadata.get("catchup") and metadata.get("crossover_time"):
        crossover = _parse_instant(metadata.get("crossover_time"))
        if crossover is not None:
            return crossover

    if bar_duration is not None:
        implied = _implied_candle_open_at_analysis(run, bar_duration)
        if implied is not None:
            return implied

    candle = _parse_instant(run.get("candle_time"))
    if candle is not None:
        return candle
    crossover = _parse_instant(metadata.get("crossover_time"))
    if crossover is not None:
        return crossover
    return _parse_instant(run.get("analyzed_at"))


def _implied_candle_open_at_analysis(
    run: dict[str, Any],
    bar_duration: timedelta,
) -> datetime | None:
    """When analysis ran just after a bar close, return that bar's open time."""
    analyzed = _parse_instant(run.get("analyzed_at"))
    if analyzed is None:
        return None

    analyzed_utc = analyzed.astimezone(timezone.utc)
    at_ms = int(analyzed_utc.timestamp() * 1000)
    tf_ms = int(bar_duration.total_seconds() * 1000)
    if tf_ms <= 0:
        return None

    ms_into_bar = at_ms % tf_ms
    if ms_into_bar > 120_000:
        return None

    implied_open_ms = at_ms - ms_into_bar - tf_ms
    stored = _parse_instant(run.get("candle_time"))
    if stored is None:
        return datetime.fromtimestamp(implied_open_ms / 1000, tz=timezone.utc)

    stored_ms = int(stored.astimezone(timezone.utc).timestamp() * 1000)
    if stored_ms < implied_open_ms:
        return datetime.fromtimestamp(implied_open_ms / 1000, tz=timezone.utc)
    return None


def _resolve_anchor_candle_index(candles: list[dict[str, Any]], candle_time: datetime) -> int:
    """Return the analyzed bar index, or the last bar at/before ``candle_time``."""
    if not candles:
        return 0

    anchor_key = int(candle_time.timestamp() * 1000)
    best_idx = len(candles) - 1
    for idx, candle in enumerate(candles):
        opened = _candle_open_time(candle)
        if opened is None:
            continue
        bar_key = int(opened.timestamp() * 1000)
        if bar_key == anchor_key:
            return idx
        if bar_key <= anchor_key:
            best_idx = idx
    return best_idx


async def _resolve_analysis_warmup_bars(run: dict[str, Any]) -> int:
    """Bars of history before the analyzed candle required for indicator warmup."""
    stored = int(run.get("min_candles") or 0)
    strategy_id = str(run.get("strategy_id") or "").strip()
    if not strategy_id:
        return stored

    strategy = await StrategiesRepository().get_by_id(strategy_id)
    if not strategy:
        return stored

    params = strategy.get("params") or {}
    try:
        normalized = strategy_params(strategy)
        resolved = effective_min_candles(normalized)
    except Exception:
        if stored > 0:
            return stored
        return compute_required_candles(params)
    return max(stored, resolved)


@router.get("")
async def list_strategy_analysis_runs(
    _username: str = Depends(require_auth),
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None),
    strategy_id: str | None = Query(default=None),
    pair: str | None = Query(default=None),
    analysis_purpose: str | None = Query(default=None),
) -> JSONResponse:
    before_dt: datetime | None = None
    if before:
        try:
            before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            before_dt = None

    repo = StrategyAnalysisRunsRepository()
    purpose = analysis_purpose if analysis_purpose in {"entry", "exit"} else None
    runs = await repo.list_recent(
        strategy_id=strategy_id,
        pair=pair,
        analysis_purpose=purpose,
        limit=limit,
        before=before_dt,
    )
    return JSONResponse({"runs": runs, "latest": runs[0] if runs else None})


@router.post("/run")
async def run_manual_strategy_analysis_route(
    body: RunManualAnalysisBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    """Run a single strategy analysis for one symbol on demand."""
    try:
        run = await run_manual_strategy_analysis(
            strategy_id=body.strategy_id.strip(),
            asset_class=body.asset_class.strip(),
            symbol=body.symbol.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Manual strategy analysis failed")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Manual strategy analysis failed")
        raise HTTPException(
            status_code=503,
            detail="Analysis failed. Check your OANDA connection in Settings.",
        ) from exc

    return JSONResponse(run)


@router.get("/{run_id}")
async def get_strategy_analysis_run(
    run_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = StrategyAnalysisRunsRepository()
    run = await repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return JSONResponse(run)


@router.delete("/{run_id}")
async def delete_strategy_analysis_run(
    run_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = StrategyAnalysisRunsRepository()
    deleted = await repo.delete_by_id(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return JSONResponse({"id": run_id, "status": "deleted"})


@router.get("/{run_id}/candles")
async def get_strategy_analysis_run_candles(
    run_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    """Fetch OANDA candles for an analysis run chart (display window + warmup history)."""
    repo = StrategyAnalysisRunsRepository()
    run = await repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    pair = str(run.get("pair") or "").strip()
    if not pair:
        raise HTTPException(status_code=400, detail="Analysis pair is unavailable")

    timeframe = str(run.get("timeframe") or "M15")
    validate_timeframe(timeframe)
    bar_duration = timeframe_to_duration(timeframe)

    anchor_time = _analysis_signal_anchor_time(run, bar_duration=bar_duration)
    if anchor_time is None:
        raise HTTPException(status_code=400, detail="Analysis candle time is unavailable")

    warmup_bars = await _resolve_analysis_warmup_bars(run)
    display_bars_before = max(ANALYSIS_DISPLAY_BARS_BEFORE, warmup_bars)
    analyzed_at = _parse_instant(run.get("analyzed_at")) or anchor_time
    bars_to_analyzed = _bars_since_anchor(
        anchor_time,
        now=analyzed_at,
        bar_duration=bar_duration,
    )
    tail_bars = max(ANALYSIS_DISPLAY_BARS_AFTER + 2, bars_to_analyzed)
    fetch_bars = display_bars_before + warmup_bars + tail_bars

    service = require_data_manager_service()
    try:
        candles = await service.fetch_live_candles_from_oanda(
            pair,
            timeframe,
            fetch_bars,
            until=anchor_time,
            price="M",
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Analysis run candle fetch failed for %s", run_id)
        raise HTTPException(
            status_code=503,
            detail="Candle data unavailable. Check your OANDA connection in Settings.",
        ) from exc

    if not candles:
        raise HTTPException(
            status_code=503,
            detail="Candle data unavailable. Check your OANDA connection in Settings.",
        )

    anchor_idx = _resolve_anchor_candle_index(candles, anchor_time)
    display_start_idx = max(0, anchor_idx - display_bars_before)
    display_end_idx = min(len(candles) - 1, anchor_idx + ANALYSIS_DISPLAY_BARS_AFTER)

    since_dt = _candle_open_time(candles[0])
    display_since_dt = _candle_open_time(candles[display_start_idx])
    display_until_dt = _candle_open_time(candles[display_end_idx])
    last_dt = _candle_open_time(candles[-1])
    until_dt = (last_dt + bar_duration) if last_dt is not None else analyzed_at + bar_duration

    if since_dt is None or display_since_dt is None or display_until_dt is None:
        raise HTTPException(status_code=503, detail="Candle data unavailable for this analysis window.")

    return JSONResponse(
        {
            "symbol": pair,
            "timeframe": timeframe,
            "price_side": "M",
            "source": OANDA_SOURCE,
            "since": since_dt.isoformat(),
            "until": until_dt.isoformat(),
            "display_since": display_since_dt.isoformat(),
            "display_until": display_until_dt.isoformat(),
            "warmup_bars": warmup_bars,
            "candles": [serialize_candle(candle) for candle in candles],
        }
    )
