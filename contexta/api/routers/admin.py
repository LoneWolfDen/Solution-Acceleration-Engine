"""GET /api/admin/health, GET /api/admin/config, POST /api/admin/config."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_db
from ..schemas import (
    AdminConfigResponse,
    AdminConfigUpdateRequest,
    AdminConfigUpdateResponse,
    AdminHealthResponse,
    ProviderStatuses,
    ThresholdSettings,
)

router = APIRouter(tags=["admin"])

# ── Sentinel value stored in DB to indicate a key is set (never store raw keys) ──
_KEY_SET_SENTINEL = "__SET__"

# ── Default threshold values ──────────────────────────────────────────────────
_DEFAULT_THRESHOLDS = {"risk": 0.7, "constraint": 0.7, "dependency": 0.7}
_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_MAX_ACTIVE_PROJECTS = 10

# ── Provider env var names ─────────────────────────────────────────────────────
_PROVIDER_ENV_VARS = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_config_value(db: aiosqlite.Connection, key: str, default: str) -> str:
    cursor = await db.execute(
        "SELECT value FROM llm_config WHERE key = ?", (key,)
    )
    row = await cursor.fetchone()
    return row["value"] if row else default


async def _set_config_value(db: aiosqlite.Connection, key: str, value: str) -> None:
    now = _now_iso()
    await db.execute(
        """
        INSERT INTO llm_config (key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, now),
    )
    await db.commit()


def _provider_status(provider: str, db_value: str) -> str:
    """Return 'configured' / 'not_set' by checking DB sentinel then env var."""
    if db_value == _KEY_SET_SENTINEL:
        return "configured"
    env_key = _PROVIDER_ENV_VARS.get(provider, "")
    if env_key and os.environ.get(env_key, "").strip():
        return "configured"
    return "not_set"


@router.get("/admin/health", response_model=AdminHealthResponse)
async def admin_health(db: aiosqlite.Connection = Depends(get_db)) -> AdminHealthResponse:
    """Return provider connectivity status and last pipeline run timestamp."""
    groq_val = await _get_config_value(db, "api_key_groq", "")
    openrouter_val = await _get_config_value(db, "api_key_openrouter", "")
    gemini_val = await _get_config_value(db, "api_key_gemini", "")
    ollama_url = await _get_config_value(db, "ollama_url", _DEFAULT_OLLAMA_URL)

    # Last run: most recent completed review.
    cursor = await db.execute(
        "SELECT MAX(run_date) AS last_run FROM reviews WHERE status = 'complete'"
    )
    row = await cursor.fetchone()
    last_run = row["last_run"] if row else None

    # Ollama status: configured if non-default URL set OR env var present.
    ollama_env = os.environ.get("OLLAMA_BASE_URL", "").strip()
    ollama_status = (
        "configured"
        if (ollama_url != _DEFAULT_OLLAMA_URL or ollama_env)
        else "not_set"
    )

    return AdminHealthResponse(
        last_run=last_run,
        providers=ProviderStatuses(
            groq=_provider_status("groq", groq_val),
            openrouter=_provider_status("openrouter", openrouter_val),
            gemini=_provider_status("gemini", gemini_val),
            ollama=ollama_status,
        ),
        error=None,
    )


@router.get("/admin/config", response_model=AdminConfigResponse)
async def get_admin_config(db: aiosqlite.Connection = Depends(get_db)) -> AdminConfigResponse:
    """Return current configuration — API keys shown as 'set' / 'not_set', never raw."""
    groq_val = await _get_config_value(db, "api_key_groq", "")
    openrouter_val = await _get_config_value(db, "api_key_openrouter", "")
    gemini_val = await _get_config_value(db, "api_key_gemini", "")
    ollama_url = await _get_config_value(db, "ollama_url", _DEFAULT_OLLAMA_URL)

    risk = float(await _get_config_value(db, "threshold_risk", str(_DEFAULT_THRESHOLDS["risk"])))
    constraint = float(
        await _get_config_value(db, "threshold_constraint", str(_DEFAULT_THRESHOLDS["constraint"]))
    )
    dependency = float(
        await _get_config_value(db, "threshold_dependency", str(_DEFAULT_THRESHOLDS["dependency"]))
    )

    def _mask(val: str, provider: str) -> str:
        if val == _KEY_SET_SENTINEL:
            return "set"
        env_key = _PROVIDER_ENV_VARS.get(provider, "")
        if env_key and os.environ.get(env_key, "").strip():
            return "set"
        return "not_set"

    return AdminConfigResponse(
        providers={
            "groq": _mask(groq_val, "groq"),
            "openrouter": _mask(openrouter_val, "openrouter"),
            "gemini": _mask(gemini_val, "gemini"),
        },
        ollama_url=ollama_url,
        thresholds=ThresholdSettings(risk=risk, constraint=constraint, dependency=dependency),
        max_active_projects=_DEFAULT_MAX_ACTIVE_PROJECTS,
        error=None,
    )


@router.post("/admin/config", response_model=AdminConfigUpdateResponse)
async def update_admin_config(
    body: AdminConfigUpdateRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> AdminConfigUpdateResponse:
    """Save an API key, threshold value, or Ollama URL."""
    if body.field == "api_key":
        if not body.provider:
            raise HTTPException(status_code=422, detail="provider is required for field='api_key'.")
        if body.provider not in ("groq", "openrouter", "gemini"):
            raise HTTPException(
                status_code=422,
                detail=f"Unknown provider '{body.provider}'. Must be groq, openrouter, or gemini.",
            )
        if not body.key:
            raise HTTPException(status_code=422, detail="key is required for field='api_key'.")
        # Store sentinel — never persist raw keys.
        await _set_config_value(db, f"api_key_{body.provider}", _KEY_SET_SENTINEL)

    elif body.field == "threshold":
        if not body.threshold_name:
            raise HTTPException(
                status_code=422, detail="threshold_name is required for field='threshold'."
            )
        if body.threshold_name not in ("risk", "constraint", "dependency"):
            raise HTTPException(
                status_code=422,
                detail=f"Unknown threshold '{body.threshold_name}'. Must be risk, constraint, or dependency.",
            )
        if body.threshold_value is None:
            raise HTTPException(
                status_code=422, detail="threshold_value is required for field='threshold'."
            )
        await _set_config_value(db, f"threshold_{body.threshold_name}", str(body.threshold_value))

    elif body.field == "ollama_url":
        if not body.ollama_url:
            raise HTTPException(
                status_code=422, detail="ollama_url is required for field='ollama_url'."
            )
        await _set_config_value(db, "ollama_url", body.ollama_url)

    else:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown field '{body.field}'. Must be api_key, threshold, or ollama_url.",
        )

    return AdminConfigUpdateResponse(field=body.field, status="saved", error=None)
