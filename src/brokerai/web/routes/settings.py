from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from brokerai.config.env_file import config_file_path, config_file_writable, save_update_env_values
from brokerai.config_backup.change_labels import describe_system_update_change
from brokerai.config_backup.hooks import auto_backup_before
from brokerai.config.settings import UpdateTrack, get_settings, reload_settings
from brokerai.web.domain_tls import (
    apply_domain_tls,
    domain_tls_apply_available,
    read_domain_settings,
    valid_hostname,
)
from brokerai.web.routes.auth import require_auth
from brokerai.web.update_runner import clear_update_check_cache, is_dev_install

router = APIRouter(prefix="/api/settings", tags=["settings"])


class UpdateSettingsBody(BaseModel):
    update_track: UpdateTrack
    branch: str = Field(default="main", max_length=120)
    release: str = Field(default="", max_length=120)
    auto_update: bool = True

    @field_validator("branch", "release")
    @classmethod
    def strip_value(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_track_fields(self) -> "UpdateSettingsBody":
        if self.update_track == "release" and not self.release:
            raise ValueError("release is required when update_track is release")
        return self


def _update_settings_payload() -> dict:
    settings = get_settings()
    path = config_file_path()
    display_path = ".env" if path.name == ".env" else str(path)
    return {
        "update_track": settings.update_track,
        "branch": settings.branch,
        "release": settings.release or "",
        "repo": settings.repo,
        "auto_update": settings.auto_update,
        "configured_pin": settings.update_pin_display,
        "config_path": display_path,
        "config_writable": config_file_writable(),
    }


@router.get("/update")
async def get_update_settings(_username: str = Depends(require_auth)) -> JSONResponse:
    reload_settings()
    return JSONResponse(_update_settings_payload())


@router.put("/update")
async def put_update_settings(
    body: UpdateSettingsBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    if not config_file_writable():
        path = config_file_path()
        raise HTTPException(
            status_code=403,
            detail=f"Cannot write {path}. Edit the file manually or adjust permissions.",
        )

    settings = get_settings()
    auto_update = body.auto_update if body.update_track != "release" else False
    change_label = describe_system_update_change(
        {
            "update_track": settings.update_track,
            "branch": settings.branch,
            "release": settings.release or "",
            "auto_update": settings.auto_update,
        },
        update_track=body.update_track,
        branch=body.branch,
        release=body.release,
        auto_update=auto_update,
    )

    await auto_backup_before(
        trigger="settings.update",
        summary="System update settings",
        change_label=change_label or "System update settings",
    )

    try:
        saved_path = save_update_env_values(
            update_track=body.update_track,
            branch=body.branch,
            release=body.release,
            repo=settings.repo,
            auto_update=auto_update,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {exc}") from exc

    reload_settings()
    clear_update_check_cache()
    payload = _update_settings_payload()
    payload["saved_to"] = str(saved_path)
    return JSONResponse(payload)


class DomainSettingsBody(BaseModel):
    domain: str = Field(default="", max_length=253)
    supabase_domain: str = Field(default="", max_length=253)

    @field_validator("domain", "supabase_domain")
    @classmethod
    def strip_hostname(cls, value: str) -> str:
        return value.strip().lower()


def _domain_settings_payload() -> dict:
    settings = get_settings()
    path = config_file_path()
    display_path = ".env" if path.name == ".env" else str(path)
    current = read_domain_settings()
    return {
        "domain": current["domain"],
        "supabase_domain": current["supabase_domain"],
        "supabase_url": current["supabase_url"],
        "config_path": display_path,
        "apply_available": domain_tls_apply_available(settings),
        "dev_mode": is_dev_install(settings),
    }


@router.get("/domain")
async def get_domain_settings(_username: str = Depends(require_auth)) -> JSONResponse:
    return JSONResponse(_domain_settings_payload())


@router.post("/domain/apply")
async def post_domain_settings_apply(
    body: DomainSettingsBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    if not body.domain:
        raise HTTPException(status_code=400, detail="BrokerAI domain is required")
    if not valid_hostname(body.domain):
        raise HTTPException(
            status_code=400,
            detail="Invalid BrokerAI domain (use a hostname like broker.example.com)",
        )
    if body.supabase_domain and not valid_hostname(body.supabase_domain):
        raise HTTPException(
            status_code=400,
            detail="Invalid Supabase domain (use a hostname like supabase.example.com)",
        )

    await auto_backup_before(
        trigger="settings.domain",
        summary="Public domain / TLS settings",
        change_label=(
            f"Domain → {body.domain}"
            + (f", Supabase → {body.supabase_domain}" if body.supabase_domain else "")
        ),
    )

    ok, message = await apply_domain_tls(
        domain=body.domain,
        supabase_domain=body.supabase_domain,
    )
    if not ok:
        raise HTTPException(status_code=500, detail=message)

    payload = _domain_settings_payload()
    # Reflect requested values even if process env has not reloaded yet (web restart).
    payload["domain"] = body.domain
    payload["supabase_domain"] = body.supabase_domain
    if body.supabase_domain:
        payload["supabase_url"] = f"https://{body.supabase_domain}"
    payload["message"] = message
    payload["status"] = "applied"
    return JSONResponse(payload)
