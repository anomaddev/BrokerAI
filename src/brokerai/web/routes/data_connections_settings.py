from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brokerai.bots.researcher.news import test_newsapi
from brokerai.integrations.massive import test_massive
from brokerai.provider_capabilities import supports_capability
from brokerai.db.repositories.ai_models import AiModelsRepository, mask_api_key
from brokerai.db.repositories.data_connections import DataConnectionsRepository
from brokerai.web.routes.auth import require_auth

router = APIRouter(prefix="/api/settings/data-connections", tags=["settings-data-connections"])


class NewsApiBody(BaseModel):
    api_key: str = Field(default="", max_length=500)
    enabled: bool = True


class NewsApiTestBody(BaseModel):
    api_key: str = Field(default="", max_length=500)


class MassiveBody(BaseModel):
    api_key: str = Field(default="", max_length=500)
    enabled: bool = True


class MassiveTestBody(BaseModel):
    api_key: str = Field(default="", max_length=500)


class ModelCapabilitiesBody(BaseModel):
    capabilities: dict[str, bool] = Field(default_factory=dict)


def _public_api_key_connection(doc: dict, *, default_type: str) -> dict:
    return {
        "type": doc.get("type", default_type),
        "enabled": bool(doc.get("enabled")),
        "api_key": mask_api_key(doc.get("api_key") or None),
        "api_key_set": bool(doc.get("api_key")),
    }


def _public_newsapi(doc: dict) -> dict:
    return _public_api_key_connection(doc, default_type="newsapi")


def _public_massive(doc: dict) -> dict:
    return _public_api_key_connection(doc, default_type="massive")


@router.get("")
async def get_data_connections(_username: str = Depends(require_auth)) -> JSONResponse:
    connections_repo = DataConnectionsRepository()
    models_repo = AiModelsRepository()

    news = await connections_repo.get_newsapi()
    massive = await connections_repo.get_massive()
    models = await models_repo.list_all()
    capabilities_map = await connections_repo.get_model_capabilities_map()

    model_connections = [
        connections_repo.public_model_connection(
            model,
            capabilities_map.get(model["id"], {}),
        )
        for model in models
    ]

    return JSONResponse(
        {
            "newsapi": _public_newsapi(news),
            "massive": _public_massive(massive),
            "models": model_connections,
        }
    )


@router.put("/newsapi")
async def save_newsapi(body: NewsApiBody, _username: str = Depends(require_auth)) -> JSONResponse:
    repo = DataConnectionsRepository()
    existing = await repo.get_newsapi()
    api_key = body.api_key.strip() if body.api_key.strip() else existing.get("api_key", "")
    doc = await repo.save_newsapi(api_key=api_key, enabled=body.enabled)
    return JSONResponse(_public_newsapi(doc))


@router.delete("/newsapi")
async def delete_newsapi(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = DataConnectionsRepository()
    doc = await repo.delete_newsapi()
    return JSONResponse(_public_newsapi(doc))


@router.put("/massive")
async def save_massive(body: MassiveBody, _username: str = Depends(require_auth)) -> JSONResponse:
    repo = DataConnectionsRepository()
    existing = await repo.get_massive()
    api_key = body.api_key.strip() if body.api_key.strip() else existing.get("api_key", "")
    doc = await repo.save_massive(api_key=api_key, enabled=body.enabled)
    return JSONResponse(_public_massive(doc))


@router.delete("/massive")
async def delete_massive(_username: str = Depends(require_auth)) -> JSONResponse:
    repo = DataConnectionsRepository()
    doc = await repo.delete_massive()
    return JSONResponse(_public_massive(doc))


@router.put("/models/{model_id}")
async def save_model_capabilities(
    model_id: str,
    body: ModelCapabilitiesBody,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    models_repo = AiModelsRepository()
    connections_repo = DataConnectionsRepository()

    model = await models_repo.find_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    provider_type = str(model.get("type") or "")
    for key in body.capabilities:
        if not supports_capability(provider_type, key):
            raise HTTPException(
                status_code=400,
                detail=f"Capability '{key}' is not supported for provider type '{provider_type}'",
            )

    stored = await connections_repo.save_model_capabilities(
        model_id,
        provider_type=provider_type,
        capabilities=body.capabilities,
    )
    return JSONResponse(
        connections_repo.public_model_connection(model, stored),
    )


@router.post("/newsapi/test")
async def test_newsapi_connection(
    body: NewsApiTestBody | None = None,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = DataConnectionsRepository()
    news = await repo.get_newsapi()
    draft = body.api_key.strip() if body and body.api_key.strip() else ""
    api_key = draft if draft else news.get("api_key", "")
    ok, message = await test_newsapi(api_key)
    return JSONResponse({"ok": ok, "message": message})


@router.post("/massive/test")
async def test_massive_connection(
    body: MassiveTestBody | None = None,
    _username: str = Depends(require_auth),
) -> JSONResponse:
    repo = DataConnectionsRepository()
    massive = await repo.get_massive()
    draft = body.api_key.strip() if body and body.api_key.strip() else ""
    api_key = draft if draft else massive.get("api_key", "")
    ok, message = await test_massive(api_key)
    return JSONResponse({"ok": ok, "message": message})
