from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from brokerai.tasks import cancel_task, get_active_task, get_recent_tasks
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/active")
async def active_task(_username: str = Depends(require_auth)) -> JSONResponse:
    return JSONResponse({"task": get_active_task()})


@router.get("/recent")
async def recent_tasks(
    limit: int = Query(default=3, ge=1, le=10),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    return JSONResponse({"tasks": get_recent_tasks(limit=limit)})


@router.post("/{task_id}/cancel")
async def cancel_active_task(
    task_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    ok, error = await cancel_task(task_id)
    if not ok:
        if error == "Task not found or not active":
            raise HTTPException(status_code=404, detail=error)
        if error == "Task kind cannot be cancelled":
            raise HTTPException(status_code=409, detail=error)
        raise HTTPException(status_code=400, detail=error or "Cancel failed")
    return JSONResponse({"ok": True, "task_id": task_id})
