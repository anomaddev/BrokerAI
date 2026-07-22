from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.config_backup.change_labels import describe_strategy_update
from brokerai.config_backup.hooks import auto_backup_before
from brokerai.db.repositories.backtest_runs import BacktestRunsRepository
from brokerai.db.repositories.strategies import StrategiesRepository, clean_instrument_selection
from brokerai.db.repositories.strategy_versions import StrategyVersionsRepository
from brokerai.strategies.params import ParamsValidationError
from brokerai.strategies.registry import get_preset, list_presets, serialize_preset
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class CreateStrategyBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    preset_id: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    instrument_selection: dict[str, list[str]] = Field(default_factory=dict)
    enabled: bool = False


class UpdateStrategyBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    params: dict[str, Any] | None = None
    instrument_selection: dict[str, list[str]] | None = None
    enabled: bool | None = None


class QueueBacktestBody(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=120)
    instrument: str | None = Field(default=None, max_length=32)
    period: str = Field(default="6m", max_length=8)
    verbose: bool = False
    account_margin: float | None = None


@router.get("/presets")
async def list_strategy_presets(_username: str = Depends(require_auth)) -> JSONResponse:
    presets = [serialize_preset(p) for p in list_presets()]
    return JSONResponse({"presets": presets})


@router.get("")
async def list_strategies(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = StrategiesRepository()
    return JSONResponse({"strategies": await repo.list_all()})


@router.post("/backtest")
async def queue_strategy_backtests(
    body: QueueBacktestBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    from brokerai.backtesting.periods import resolve_period_window
    from brokerai.db.repositories.backtest_runs import (
        BACKTEST_PERIODS,
        normalize_account_margin,
        normalize_backtest_period,
    )

    ids = [strategy_id.strip() for strategy_id in body.ids if strategy_id and strategy_id.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="Select at least one strategy")

    period_raw = (body.period or "6m").strip()
    if period_raw not in BACKTEST_PERIODS:
        raise HTTPException(status_code=400, detail="Invalid period")
    period = normalize_backtest_period(period_raw)
    account_margin = normalize_account_margin(body.account_margin)

    repo = StrategiesRepository()
    strategies = await repo.queue_backtests(ids)
    if not strategies:
        raise HTTPException(status_code=404, detail="No matching strategies found")

    start, end = resolve_period_window(period)
    runs_repo = BacktestRunsRepository()
    runs = await runs_repo.create_queued_runs(
        strategies,
        name=body.name,
        instrument=body.instrument,
        period=period,
        verbose=body.verbose,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        account_margin=account_margin,
    )
    return JSONResponse({"strategies": strategies, "queued": len(strategies), "runs": runs})


@router.get("/{strategy_id}/versions")
async def list_strategy_versions(
    strategy_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    strategies = StrategiesRepository()
    if not await strategies.get_by_id(strategy_id):
        raise HTTPException(status_code=404, detail="Strategy not found")
    versions, total = await StrategyVersionsRepository().list_for_strategy(
        strategy_id,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(
        {
            "versions": versions,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


@router.get("/{strategy_id}/versions/{version_id}")
async def get_strategy_version(
    strategy_id: str,
    version_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    strategies = StrategiesRepository()
    if not await strategies.get_by_id(strategy_id):
        raise HTTPException(status_code=404, detail="Strategy not found")
    version = await StrategyVersionsRepository().get_by_id(strategy_id, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Strategy version not found")
    return JSONResponse(version)


@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = StrategiesRepository()
    doc = await repo.get_by_id(strategy_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return JSONResponse(doc)


@router.post("")
async def create_strategy(
    body: CreateStrategyBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    preset = get_preset(body.preset_id)
    if not preset:
        raise HTTPException(status_code=400, detail="Unknown strategy preset")

    selection = clean_instrument_selection(body.instrument_selection)
    if not selection:
        raise HTTPException(status_code=400, detail="Select at least one instrument")

    await auto_backup_before(
        trigger="strategies.create",
        summary=f"Create strategy: {body.name.strip()}",
        change_label=f"Added strategy: {body.name.strip()}",
    )

    repo = StrategiesRepository()
    try:
        doc = await repo.create(
            name=body.name,
            description=body.description,
            preset_id=body.preset_id,
            params=body.params,
            instrument_selection=selection,
            enabled=body.enabled,
        )
    except ParamsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Create-time AI Strategy bootstrap (reports → seed digest → improve loops).
    try:
        from brokerai.ai_strategy.lifecycle import is_ai_strategy_doc
        from brokerai.ai_strategy.startup import enqueue_ai_strategy_startup

        if is_ai_strategy_doc(doc):
            await enqueue_ai_strategy_startup(str(doc.get("id") or ""))
    except Exception:
        # Never fail create if startup enqueue has a transient error.
        import logging

        logging.getLogger(__name__).exception(
            "Failed to enqueue AI Strategy startup for %s", doc.get("id")
        )

    return JSONResponse(doc)


@router.patch("/{strategy_id}")
async def update_strategy(
    strategy_id: str,
    body: UpdateStrategyBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    if (
        body.name is None
        and body.description is None
        and body.params is None
        and body.instrument_selection is None
        and body.enabled is None
    ):
        raise HTTPException(status_code=400, detail="No fields to update")

    selection = None
    if body.instrument_selection is not None:
        selection = clean_instrument_selection(body.instrument_selection)
        if not selection:
            raise HTTPException(status_code=400, detail="Select at least one instrument")

    repo = StrategiesRepository()
    existing = await repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Strategy not found")

    change_label = describe_strategy_update(
        existing,
        name=body.name,
        description=body.description,
        params=body.params,
        instrument_selection=selection,
        enabled=body.enabled,
    )
    await auto_backup_before(
        trigger=f"strategies.patch:{strategy_id}",
        summary=f"Update strategy: {existing.get('name') or strategy_id}",
        change_label=change_label or f"Updated strategy: {existing.get('name') or strategy_id}",
    )

    try:
        doc = await repo.update(
            strategy_id,
            name=body.name,
            description=body.description,
            params=body.params,
            instrument_selection=selection,
            enabled=body.enabled,
        )
    except ParamsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not doc:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return JSONResponse(doc)


@router.post("/{strategy_id}/promote")
async def promote_ai_strategy(
    strategy_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    """Explicit ready → live promotion for AI Strategies."""
    repo = StrategiesRepository()
    existing = await repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Strategy not found")
    try:
        doc = await repo.promote_to_live(strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not doc:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return JSONResponse(doc)


@router.get("/{strategy_id}/startup")
async def get_strategy_startup(
    strategy_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    from brokerai.db.repositories.ai_strategy_startup import AiStrategyStartupJobsRepository

    if not await StrategiesRepository().get_by_id(strategy_id):
        raise HTTPException(status_code=404, detail="Strategy not found")
    job = await AiStrategyStartupJobsRepository().get_latest_for_strategy(strategy_id)
    return JSONResponse({"job": job})


@router.post("/{strategy_id}/startup")
async def retry_strategy_startup(
    strategy_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    from brokerai.ai_strategy.lifecycle import is_ai_strategy_doc
    from brokerai.ai_strategy.startup import enqueue_ai_strategy_startup

    repo = StrategiesRepository()
    existing = await repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if not is_ai_strategy_doc(existing):
        raise HTTPException(status_code=400, detail="Not an AI Strategy")
    job = await enqueue_ai_strategy_startup(strategy_id, force=True)
    if job is None:
        raise HTTPException(status_code=400, detail="Startup is disabled in Settings → AI Strategies")
    return JSONResponse({"job": job})


@router.delete("/{strategy_id}")
async def delete_strategy(
    strategy_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = StrategiesRepository()
    existing = await repo.get_by_id(strategy_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Strategy not found")

    strategy_name = str(existing.get("name") or strategy_id)
    await auto_backup_before(
        trigger=f"strategies.delete:{strategy_id}",
        summary=f"Delete strategy: {strategy_name}",
        change_label=f"Removed strategy: {strategy_name}",
    )

    deleted = await repo.delete(strategy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return JSONResponse({"status": "deleted", "id": strategy_id})
