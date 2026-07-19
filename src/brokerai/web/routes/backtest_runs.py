"""HTTP routes for strategy backtest run history."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from brokerai.db.repositories.backtest_runs import (
    BACKTEST_RUN_STATUSES,
    BacktestRunsRepository,
)
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/backtest-runs", tags=["backtest-runs"])


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


@router.delete("/{run_id}")
async def delete_backtest_run(
    run_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = BacktestRunsRepository()
    deleted = await repo.delete_by_id(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return JSONResponse({"id": run_id, "status": "deleted"})
