"""
contexta/api/routers/admin.py

GET  /api/admin/health
GET  /api/admin/config
POST /api/admin/config
"""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from ..config_store import AdminConfigStore
from ..dependencies import get_config, get_db
from ..schemas import (
    AdminConfigRequest,
    AdminConfigResponse,
    AdminConfigSaveResponse,
    AdminHealthResponse,
    ProviderKeyStatuses,
    ProviderStatuses,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_SUPPORTED_PROVIDERS = ("groq", "openrouter", "gemini")
_SUPPORTED_THRESHOLDS = ("risk", "constraint", "dependency")


@router.get("/health", response_model=AdminHealthResponse)
async def admin_health(
    config: AdminConfigStore = Depends(get_config),
) -> AdminHealthResponse:
    return AdminHealthResponse(
        last_run=config.last_run,
        providers=ProviderStatuses(
            groq=config.provider_connectivity_status("groq"),
            openrouter=config.provider_connectivity_status("openrouter"),
            gemini=config.provider_connectivity_status("gemini"),
            ollama=config.provider_connectivity_status("ollama"),
        ),
        error=None,
    )


@router.get("/config", response_model=AdminConfigResponse)
async def admin_config(
    config: AdminConfigStore = Depends(get_config),
) -> AdminConfigResponse:
    return AdminConfigResponse(
        providers=ProviderKeyStatuses(
            groq=config.key_status("groq"),
            openrouter=config.key_status("openrouter"),
            gemini=config.key_status("gemini"),
        ),
        ollama_url=config.ollama_url,
        thresholds=dict(config.thresholds),
        max_active_projects=config.max_active_projects,
        error=None,
    )


@router.post("/config", response_model=AdminConfigSaveResponse)
async def update_admin_config(
    body: AdminConfigRequest,
    config: AdminConfigStore = Depends(get_config),
) -> AdminConfigSaveResponse:
    if body.field == "api_key":
        if not body.provider:
            raise HTTPException(
                status_code=422, detail="provider is required when field='api_key'."
            )
        if body.provider not in _SUPPORTED_PROVIDERS:
            raise HTTPException(
                status_code=422,
                detail=f"provider must be one of {_SUPPORTED_PROVIDERS}.",
            )
        if body.key is None:
            raise HTTPException(
                status_code=422, detail="key is required when field='api_key'."
            )
        config.set_key(body.provider, body.key)

    elif body.field == "threshold":
        if not body.threshold_name:
            raise HTTPException(
                status_code=422,
                detail="threshold_name is required when field='threshold'.",
            )
        if body.threshold_name not in _SUPPORTED_THRESHOLDS:
            raise HTTPException(
                status_code=422,
                detail=f"threshold_name must be one of {_SUPPORTED_THRESHOLDS}.",
            )
        if body.threshold_value is None:
            raise HTTPException(
                status_code=422,
                detail="threshold_value is required when field='threshold'.",
            )
        if not (0.0 <= body.threshold_value <= 1.0):
            raise HTTPException(
                status_code=422,
                detail="threshold_value must be between 0.0 and 1.0.",
            )
        config.set_threshold(body.threshold_name, body.threshold_value)

    elif body.field == "ollama_url":
        if not body.ollama_url:
            raise HTTPException(
                status_code=422,
                detail="ollama_url is required when field='ollama_url'.",
            )
        config.ollama_url = body.ollama_url

    else:
        raise HTTPException(
            status_code=422,
            detail="field must be one of 'api_key', 'threshold', 'ollama_url'.",
        )

    return AdminConfigSaveResponse(field=body.field, status="saved", error=None)
