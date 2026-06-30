from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from brokerai.db.repositories.strategy_analysis_runs import StrategyAnalysisRunsRepository
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/strategy-analysis-runs", tags=["strategy-analysis-runs"])


@router.get("")
async def list_strategy_analysis_runs(
    _username: str = Depends(require_auth),
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None),
    strategy_id: str | None = Query(default=None),
    pair: str | None = Query(default=None),
) -> JSONResponse:
    before_dt: datetime | None = None
    if before:
        try:
            before_dt = datetime.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            before_dt = None

    repo = StrategyAnalysisRunsRepository()
    runs = await repo.list_recent(
        strategy_id=strategy_id,
        pair=pair,
        limit=limit,
        before=before_dt,
    )
    return JSONResponse({"runs": runs, "latest": runs[0] if runs else None})


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
