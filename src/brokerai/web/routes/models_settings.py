from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.bots.researcher.llm import test_model
from brokerai.config_backup.change_labels import describe_ai_model_update
from brokerai.config_backup.hooks import auto_backup_before
from brokerai.db.repositories.ai_models import AiModelsRepository, mask_api_key
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/settings/models", tags=["settings-models"])


class CreateModelBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    type: str = Field(default="open_webui", pattern="^(open_webui|openai|claude|grok)$")
    base_url: str = Field(min_length=1, max_length=500)
    model_name: str = Field(min_length=1, max_length=120)
    api_key: str = Field(default="", max_length=500)
    enabled: bool = True


class UpdateModelBody(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    model_name: str | None = Field(default=None, max_length=120)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class ToggleModelBody(BaseModel):
    enabled: bool


def _public_model(doc: dict) -> dict:
    return {
        **doc,
        "api_key": mask_api_key(doc.get("api_key") or None),
        "api_key_set": bool(doc.get("api_key")),
    }


@router.get("")
async def list_models(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = AiModelsRepository()
    models = await repo.list_all()
    return JSONResponse({"models": [_public_model(m) for m in models]})


@router.post("")
async def create_model(body: CreateModelBody, _username: str = Depends(require_auth)) -> JSONResponse:
    await auto_backup_before(
        trigger="ai_models.create",
        summary=f"Create AI model: {body.title.strip()}",
        change_label=f"Added AI model: {body.title.strip()}",
    )
    repo = AiModelsRepository()
    doc = await repo.create(
        title=body.title,
        model_type=body.type,
        base_url=body.base_url,
        model_name=body.model_name,
        api_key=body.api_key or None,
        enabled=body.enabled,
    )
    return JSONResponse(_public_model(doc))


@router.put("/{model_id}")
async def update_model(
    model_id: str,
    body: UpdateModelBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = AiModelsRepository()
    existing = await repo.find_by_id(model_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Model not found")

    api_key_changed = bool(
        body.api_key is not None
        and body.api_key.strip()
        and body.api_key != existing.get("api_key", "")
    )
    change_label = describe_ai_model_update(
        existing,
        title=body.title,
        base_url=body.base_url,
        model_name=body.model_name,
        enabled=body.enabled,
        api_key_changed=api_key_changed,
    )
    await auto_backup_before(
        trigger=f"ai_models.update:{model_id}",
        summary=f"Update AI model: {existing.get('title') or model_id}",
        change_label=change_label or f"Updated AI model: {existing.get('title') or model_id}",
    )

    api_key = body.api_key
    if api_key == "":
        api_key = existing.get("api_key", "")

    doc = await repo.update(
        model_id,
        title=body.title,
        base_url=body.base_url,
        model_name=body.model_name,
        api_key=api_key,
        enabled=body.enabled,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Model not found")
    return JSONResponse(_public_model(doc))


@router.patch("/{model_id}")
async def toggle_model(
    model_id: str,
    body: ToggleModelBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = AiModelsRepository()
    existing = await repo.find_by_id(model_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Model not found")

    model_title = str(existing.get("title") or model_id)
    change_label = describe_ai_model_update(
        existing,
        title=None,
        base_url=None,
        model_name=None,
        enabled=body.enabled,
        api_key_changed=False,
    )
    await auto_backup_before(
        trigger=f"ai_models.toggle:{model_id}",
        summary=f"Toggle AI model: {model_title}",
        change_label=change_label or f"Updated AI model: {model_title}",
    )

    doc = await repo.set_enabled(model_id, body.enabled)
    if not doc:
        raise HTTPException(status_code=404, detail="Model not found")
    return JSONResponse(_public_model(doc))


@router.post("/test-connection")
async def test_connection(body: CreateModelBody, _username: str = Depends(require_auth)) -> JSONResponse:
    ok, message = await test_model(
        body.type,
        body.base_url,
        body.model_name,
        body.api_key or None,
    )
    return JSONResponse({"ok": ok, "message": message})


@router.post("/{model_id}/test")
async def test_saved_model(model_id: str, _username: str = Depends(require_auth)) -> JSONResponse:
    repo = AiModelsRepository()
    doc = await repo.find_by_id(model_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Model not found")

    ok, message = await test_model(
        doc["type"],
        doc["base_url"],
        doc["model_name"],
        doc.get("api_key") or None,
    )
    return JSONResponse({"ok": ok, "message": message})


@router.delete("/{model_id}")
async def delete_model(model_id: str, _username: str = Depends(require_auth)) -> JSONResponse:
    repo = AiModelsRepository()
    existing = await repo.find_by_id(model_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Model not found")

    model_title = str(existing.get("title") or model_id)
    await auto_backup_before(
        trigger=f"ai_models.delete:{model_id}",
        summary=f"Delete AI model: {model_title}",
        change_label=f"Removed AI model: {model_title}",
    )

    ok = await repo.delete_with_cleanup(model_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Model not found")
    return JSONResponse({"ok": True})
