"""
contexta/api/routers/admin.py

GET  /api/admin/health   — provider connectivity status + last run
GET  /api/admin/config   — current config (keys masked, never raw)
POST /api/admin/config   — save one config field (key, threshold, ollama_url, etc.)
"""

from __future__ import annotations

import logging
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from contexta.api import repositories as api_repo
from contexta.api import schemas
from contexta.api.config_keys import (
    KEY_GEMINI as _KEY_GEMINI,
    KEY_GROQ as _KEY_GROQ,
    KEY_MAX_ACTIVE_PROJECTS as _KEY_MAX_ACTIVE_PROJECTS,
    KEY_OLLAMA_URL as _KEY_OLLAMA_URL,
    KEY_OPENROUTER as _KEY_OPENROUTER,
    KEY_THRESHOLD_CONSTRAINT as _KEY_THRESHOLD_CONSTRAINT,
    KEY_THRESHOLD_DEPENDENCY as _KEY_THRESHOLD_DEPENDENCY,
    KEY_THRESHOLD_RISK as _KEY_THRESHOLD_RISK,
    PROVIDER_KEYS as _PROVIDER_KEYS,
)
from contexta.api.dependencies import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _status(value: Optional[str]) -> str:
    return "configured" if value else "not_set"


def _key_status(value: Optional[str]) -> str:
    return "set" if value else "not_set"


@router.get("/health", response_model=schemas.AdminHealthResponse)
async def get_health(
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.AdminHealthResponse:
    """Return live provider status and the timestamp of the last completed review."""
    config = await api_repo.get_all_config(conn)

    # Last completed review timestamp
    cursor = await conn.execute(
        "SELECT updated_at FROM review_jobs WHERE status = 'complete' "
        "ORDER BY updated_at DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    last_run: Optional[str] = row["updated_at"] if row else None

    return schemas.AdminHealthResponse(
        last_run=last_run,
        providers=schemas.AdminProviders(
            groq=_status(config.get(_KEY_GROQ)),
            openrouter=_status(config.get(_KEY_OPENROUTER)),
            gemini=_status(config.get(_KEY_GEMINI)),
            ollama=_status(config.get(_KEY_OLLAMA_URL)),
        ),
    )


@router.get("/config", response_model=schemas.AdminConfigResponse)
async def get_config(
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.AdminConfigResponse:
    """Return current config.  API keys are returned as status strings, never raw values."""
    config = await api_repo.get_all_config(conn)

    def _float(key: str, default: float) -> float:
        try:
            return float(config[key]) if key in config else default
        except (ValueError, TypeError):
            return default

    def _int(key: str, default: int) -> int:
        try:
            return int(config[key]) if key in config else default
        except (ValueError, TypeError):
            return default

    return schemas.AdminConfigResponse(
        providers=schemas.AdminProviders(
            groq=_key_status(config.get(_KEY_GROQ)),
            openrouter=_key_status(config.get(_KEY_OPENROUTER)),
            gemini=_key_status(config.get(_KEY_GEMINI)),
            ollama=_key_status(config.get(_KEY_OLLAMA_URL)),
        ),
        ollama_url=config.get(_KEY_OLLAMA_URL, ""),
        thresholds=schemas.AdminThresholds(
            risk=_float(_KEY_THRESHOLD_RISK, 0.75),
            constraint=_float(_KEY_THRESHOLD_CONSTRAINT, 0.70),
            dependency=_float(_KEY_THRESHOLD_DEPENDENCY, 0.80),
        ),
        max_active_projects=_int(_KEY_MAX_ACTIVE_PROJECTS, 5),
    )


@router.post("/config", response_model=schemas.AdminConfigUpdateResponse)
async def update_config(
    body: schemas.UpdateAdminConfigRequest,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.AdminConfigUpdateResponse:
    """Save one configuration field.  API keys are write-only; they are never returned."""
    valid_fields = {"api_key", "threshold", "ollama_url", "max_active_projects"}
    if body.field not in valid_fields:
        raise HTTPException(
            status_code=422,
            detail=f"field must be one of {sorted(valid_fields)}.",
        )

    if body.field == "api_key":
        if not body.provider or body.provider not in _PROVIDER_KEYS:
            raise HTTPException(
                status_code=422,
                detail=f"provider must be one of {sorted(_PROVIDER_KEYS)}.",
            )
        if not body.key:
            raise HTTPException(
                status_code=422, detail="key must not be empty when saving an API key."
            )
        db_key = _PROVIDER_KEYS[body.provider]
        await api_repo.set_config_value(conn, db_key, body.key)
        logger.info("API key updated for provider: %s", body.provider)

    elif body.field == "threshold":
        valid_thresholds = {"risk", "constraint", "dependency"}
        if not body.threshold_name or body.threshold_name not in valid_thresholds:
            raise HTTPException(
                status_code=422,
                detail=f"threshold_name must be one of {sorted(valid_thresholds)}.",
            )
        if body.threshold_value is None:
            raise HTTPException(
                status_code=422, detail="threshold_value is required."
            )
        db_key = f"threshold_{body.threshold_name}"
        await api_repo.set_config_value(conn, db_key, str(body.threshold_value))
        logger.info("Threshold updated: %s = %s", body.threshold_name, body.threshold_value)

    elif body.field == "ollama_url":
        if not body.ollama_url:
            raise HTTPException(
                status_code=422, detail="ollama_url must not be empty."
            )
        await api_repo.set_config_value(conn, _KEY_OLLAMA_URL, body.ollama_url)
        logger.info("Ollama URL updated: %s", body.ollama_url)

    elif body.field == "max_active_projects":
        if body.max_active_projects is None or body.max_active_projects < 1:
            raise HTTPException(
                status_code=422, detail="max_active_projects must be >= 1."
            )
        await api_repo.set_config_value(
            conn, _KEY_MAX_ACTIVE_PROJECTS, str(body.max_active_projects)
        )
        logger.info("max_active_projects updated: %d", body.max_active_projects)

    return schemas.AdminConfigUpdateResponse(field=body.field, status="saved")
