from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.bots.researcher.report_store import SIGNED_URL_EXPIRES_IN
from brokerai.bots.researcher.reports import create_report_signed_url
from brokerai.bots.researcher.runner import (
    count_unread_reports,
    delete_report_entry,
    get_signals_snapshot,
    list_report_entries,
    mark_all_reports_read,
    mark_report_read,
    mark_report_unread,
    read_report_content,
)
from brokerai.tasks.research import (
    start_daily_report_task,
    start_daily_rerun_task,
    start_weekly_brief_task,
    start_weekly_debrief_task,
)
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/research", tags=["research"])


class RunDailyReportBody(BaseModel):
    force: bool = Field(default=True)


class RunWeeklyReportBody(BaseModel):
    force: bool = Field(default=False)


class MarkAllReadBody(BaseModel):
    filenames: list[str] | None = None


def _accepted_task_response(task_id: str) -> JSONResponse:
    return JSONResponse({"task_id": task_id, "status": "accepted"}, status_code=202)


def _conflict_response(message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "skipped_reason": message}, status_code=409)


@router.get("/reports")
async def list_reports(
    limit: int = Query(default=200, ge=1, le=200),
    username: str = Depends(require_auth),
) -> JSONResponse:
    return JSONResponse(
        {"reports": await list_report_entries(username, limit=limit)}
    )


@router.get("/signals")
async def get_signals(
    _username: str = Depends(require_auth),
) -> JSONResponse:
    return JSONResponse(await get_signals_snapshot())


@router.get("/reports/unread-count")
async def get_unread_count(
    username: str = Depends(require_auth),
) -> JSONResponse:
    return JSONResponse(await count_unread_reports(username))


@router.post("/reports/mark-read")
async def post_mark_read(
    filename: str = Query(..., min_length=1),
    username: str = Depends(require_auth),
) -> JSONResponse:
    try:
        return JSONResponse(await mark_report_read(username, filename))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Report not found: {filename}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/reports/mark-unread")
async def post_mark_unread(
    filename: str = Query(..., min_length=1),
    username: str = Depends(require_auth),
) -> JSONResponse:
    try:
        return JSONResponse(await mark_report_unread(username, filename))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Report not found: {filename}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/reports/mark-all-read")
async def post_mark_all_read(
    body: MarkAllReadBody | None = None,
    username: str = Depends(require_auth),
) -> JSONResponse:
    payload = body or MarkAllReadBody()
    return JSONResponse(
        await mark_all_reports_read(username, filenames=payload.filenames)
    )


@router.get("/reports/signed-url")
async def get_signed_url(
    filename: str = Query(..., min_length=1),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    try:
        url = await create_report_signed_url(filename, expires_in=SIGNED_URL_EXPIRES_IN)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Report not found: {filename}")
    if not url:
        raise HTTPException(
            status_code=501,
            detail="Signed URLs require Supabase Storage",
        )
    return JSONResponse(
        {
            "filename": filename,
            "signed_url": url,
            "expires_in": SIGNED_URL_EXPIRES_IN,
        }
    )


@router.get("/reports/content")
async def get_report_content(
    filename: str = Query(..., min_length=1),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    try:
        return JSONResponse(await read_report_content(filename))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Report not found: {filename}")


@router.post("/reports/run-daily")
async def run_daily_report_now(
    body: RunDailyReportBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    task_id, error = await start_daily_report_task(force=body.force, manual=True)
    if error:
        return _conflict_response(error)
    assert task_id is not None
    return _accepted_task_response(task_id)


@router.post("/reports/run-weekly-brief")
async def run_weekly_brief_now(
    body: RunWeeklyReportBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    task_id, error = await start_weekly_brief_task(force=body.force, manual=True)
    if error:
        return _conflict_response(error)
    assert task_id is not None
    return _accepted_task_response(task_id)


@router.post("/reports/run-weekly-debrief")
async def run_weekly_debrief_now(
    body: RunWeeklyReportBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    task_id, error = await start_weekly_debrief_task(force=body.force, manual=True)
    if error:
        return _conflict_response(error)
    assert task_id is not None
    return _accepted_task_response(task_id)


@router.delete("/reports")
async def delete_report(
    filename: str = Query(..., min_length=1),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    try:
        payload = await delete_report_entry(filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Report not found: {filename}")
    return JSONResponse(payload)


@router.post("/reports/rerun")
async def rerun_daily_report(
    filename: str = Query(..., min_length=1),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    try:
        meta = await read_report_content(filename, prefer_signed_url=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Report not found: {filename}")

    if meta.get("type") != "daily":
        raise HTTPException(status_code=400, detail="Only daily reports can be re-run")

    today = datetime.now(timezone.utc).date().isoformat()
    if meta.get("date") != today:
        raise HTTPException(
            status_code=400,
            detail="Only today's daily report can be re-run from the UI",
        )

    task_id, error = await start_daily_rerun_task(force=True)
    if error:
        return _conflict_response(error)
    assert task_id is not None
    return _accepted_task_response(task_id)
