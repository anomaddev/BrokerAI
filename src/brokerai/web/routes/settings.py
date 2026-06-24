from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from brokerai.config.env_file import config_file_path, config_file_writable, save_update_env_values
from brokerai.config.settings import UpdateTrack, get_settings, reload_settings
from brokerai.web.routes.auth import require_auth
from brokerai.web.update_runner import clear_update_check_cache

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
