from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.config_backup.schedule_settings import (
    get_backup_schedule_settings,
    save_backup_schedule_settings,
    schedule_settings_payload,
)
from brokerai.config_backup.service import ConfigBackupService
from brokerai.config_backup.validate import parse_import_bytes
from brokerai.config_backup.change_labels import describe_backup_schedule_change
from brokerai.config_backup.hooks import auto_backup_before
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/settings/backups", tags=["settings-backups"])


class CreateBackupBody(BaseModel):
    label: str | None = Field(default=None, max_length=120)


class RestoreBackupBody(BaseModel):
    scope: str = Field(default="full", pattern="^(setting|full)$")


class BackupScheduleBody(BaseModel):
    enabled: bool | None = None
    mode: str | None = Field(default=None, pattern="^(daily|daily_time|interval)$")
    daily_market_id: str | None = None
    daily_offset_hours: int | None = Field(default=None, ge=-6, le=6)
    daily_time: str | None = Field(default=None, pattern=r"^\d{1,2}:\d{2}$")
    interval_hours: int | None = Field(default=None, ge=1, le=48)
    full_retention: int | None = Field(default=None, ge=5, le=50)
    change_retention: int | None = Field(default=None, ge=20, le=100)


@router.get("")
async def list_backups(_username: str = Depends(require_auth)) -> JSONResponse:
    service = ConfigBackupService()
    schedule = await get_backup_schedule_settings()
    timeline = await service.list_timeline_all()
    return JSONResponse(
        {
            "timeline": timeline,
            "full_retention": schedule["full_retention"],
            "change_retention": schedule["change_retention"],
        }
    )


@router.get("/export")
async def export_current_backup(_username: str = Depends(require_auth)) -> JSONResponse:
    service = ConfigBackupService()
    record = await service.export_current()
    return JSONResponse(record)


@router.get("/schedule")
async def get_backup_schedule(_username: str = Depends(require_auth)) -> JSONResponse:
    settings = await get_backup_schedule_settings()
    return JSONResponse(schedule_settings_payload(settings))


@router.put("/schedule")
async def update_backup_schedule(
    body: BackupScheduleBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    before = await get_backup_schedule_settings()
    updates = body.model_dump(exclude_none=True)
    change_label = describe_backup_schedule_change(before, updates)
    await auto_backup_before(
        trigger="backup.schedule",
        summary="Backup schedule settings",
        change_label=change_label or "Backup schedule updated",
    )
    saved = await save_backup_schedule_settings(updates)
    return JSONResponse(schedule_settings_payload(saved))


@router.post("")
async def create_backup(
    body: CreateBackupBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    service = ConfigBackupService()
    backup = await service.create_manual_backup(label=body.label)
    return JSONResponse(backup)


@router.post("/import")
async def import_backup(
    file: UploadFile = File(...),
    label: str | None = Form(default=None),
    restore: bool = Form(default=False),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    raw = await file.read()
    try:
        payload = parse_import_bytes(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if label and len(label.strip()) > 120:
        raise HTTPException(status_code=400, detail="Label must be 120 characters or fewer")

    service = ConfigBackupService()
    result = await service.import_backup(
        payload,
        label=label.strip() if label and label.strip() else None,
        restore_immediately=restore,
    )
    return JSONResponse(result)


@router.get("/{backup_id}")
async def get_backup(
    backup_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    service = ConfigBackupService()
    backup = await service.get_backup(backup_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")
    return JSONResponse(backup)


@router.post("/{backup_id}/restore")
async def restore_backup(
    backup_id: str,
    body: RestoreBackupBody = RestoreBackupBody(),
    _username: str = Depends(require_auth),
) -> JSONResponse:
    service = ConfigBackupService()
    scope = body.scope
    try:
        result = await service.restore_backup(backup_id, scope=scope)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(result)


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: str,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    service = ConfigBackupService()
    deleted = await service.delete_backup(backup_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Backup not found")
    return JSONResponse({"ok": True})
