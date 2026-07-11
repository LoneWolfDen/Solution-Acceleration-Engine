"""
contexta/api/routers/admin.py

Existing config/health endpoints:
  GET  /api/admin/health   — provider connectivity status + last run
  GET  /api/admin/config   — current config (keys masked, never raw)
  POST /api/admin/config   — save one config field

New endpoints added in Wave 2:

  Gap 7 — JSON Import:
    POST /api/admin/import              — multipart file upload → JSONPacket validation + DB write

  Gap 8 — Dream Cycle:
    POST /api/admin/dream-cycle         — launch background worker (409 if already running)
    GET  /api/admin/dream-cycle/status  — current state, last_run timestamp, error

  Gap 9 — Blueprint Management:
    GET  /api/admin/blueprints                — list all blueprints (with prompt preview)
    POST /api/admin/blueprints                — create new blueprint (inactive by default)
    POST /api/admin/blueprints/{id}/activate  — set one blueprint active, all others inactive
"""

from __future__ import annotations

import io
import json
import logging
import uuid
from typing import Optional

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

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
from contexta.db import repositories as db_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# ── Dream Cycle in-process state ──────────────────────────────────────────────
# Module-level dict tracks the single background worker run.  A dedicated
# state store (Redis, DB row) would be overkill for an admin-only feature
# where exactly one operator triggers the cycle at a time.
_dream_cycle_state: dict = {
    "status": "idle",   # "idle" | "running" | "complete" | "failed"
    "last_run": None,   # ISO-8601 UTC string of last successful completion
    "error": None,      # last error message, or None
    "job_id": None,     # UUID of the most recently triggered cycle
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _status(value: Optional[str]) -> str:
    return "configured" if value else "not_set"


def _key_status(value: Optional[str]) -> str:
    return "set" if value else "not_set"


# ── Existing config / health ──────────────────────────────────────────────────

@router.get("/health", response_model=schemas.AdminHealthResponse)
async def get_health(
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.AdminHealthResponse:
    """Return live provider status and the timestamp of the last completed review."""
    config = await api_repo.get_all_config(conn)

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


# ── Gap 7: JSON Import ─────────────────────────────────────────────────────────

@router.post("/import", response_model=schemas.ImportResponse, status_code=201)
async def import_json_packet(
    file: UploadFile = File(...),
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ImportResponse:
    """Import a previously exported JSONPacket bundle into the database.

    Gap 7 — Requirements 7.1–7.4:
    - Reads the uploaded file bytes and validates against the ``JSONPacket``
      Pydantic schema BEFORE writing any rows (Property 13).
    - Returns HTTP 422 with validation details if the file is invalid; no DB
      write occurs.
    - On success, delegates to ``JSONPacketDeserializer`` logic (adapted to
      accept in-memory bytes rather than a file path) and returns the new
      node ID with HTTP 201.
    """
    from pathlib import Path
    from pydantic import ValidationError
    from contexta.models.export import JSONPacket
    from contexta.db.repositories import create_project, get_project, write_node

    # Read uploaded bytes.
    try:
        raw_bytes = await file.read()
        raw_text = raw_bytes.decode("utf-8")
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not read uploaded file: {exc}",
        ) from exc

    # Validate against JSONPacket schema — no DB write on failure.
    try:
        packet = JSONPacket.model_validate_json(raw_text)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"JSON Packet failed schema validation: {exc}",
        ) from exc

    if not packet.payloads:
        raise HTTPException(
            status_code=422,
            detail="JSONPacket contains no payloads; cannot import.",
        )

    # Ensure the project exists (create if absent).
    project = await get_project(conn, packet.project_id)
    if project is None:
        project = await create_project(
            conn,
            name=packet.project_name,
            global_tags=packet.global_tags,
        )

    # Build metadata and write node — all-or-nothing (single transaction via
    # write_node which calls conn.commit() after INSERT).
    metadata: dict = {
        "dimensions": [p.model_dump() for p in packet.payloads],
        "routing_decisions": packet.routing_decisions,
        "imported_from": file.filename or "upload",
        "schema_version": packet.schema_version,
        **packet.metadata,
    }
    if packet.arbitrator_result is not None:
        metadata["arbitrator_result"] = packet.arbitrator_result.model_dump()

    node_row = await write_node(
        conn,
        project_id=project.id,
        parent_id=packet.parent_node_id,
        layer_type=packet.layer_type,
        node_name=packet.node_name,
        payload=packet.payloads[0],
        metadata=metadata,
        version_tag=packet.version_tag,
    )

    logger.info(
        "[INFO] JSONPacket imported — new node '%s' (project=%s)",
        node_row.id, project.id,
    )
    return schemas.ImportResponse(node_id=node_row.id, status="imported")


# ── Gap 8: Dream Cycle ────────────────────────────────────────────────────────

async def _run_dream_cycle_task(db_path: str, job_id: str) -> None:
    """Background task: run DreamCycleWorker and update module-level state."""
    from contexta.admin.dream_cycle import DreamCycleWorker
    from contexta.db.schema import init_database
    from datetime import datetime, timezone

    conn = await init_database(db_path)
    try:
        worker = DreamCycleWorker()
        await worker.run(conn)
        _dream_cycle_state["status"] = "complete"
        _dream_cycle_state["last_run"] = datetime.now(timezone.utc).isoformat()
        _dream_cycle_state["error"] = None
        logger.info("[INFO] Dream Cycle '%s' completed successfully.", job_id)
    except Exception as exc:  # noqa: BLE001
        _dream_cycle_state["status"] = "failed"
        _dream_cycle_state["error"] = str(exc)
        logger.exception("Dream Cycle '%s' failed.", job_id)
    finally:
        await conn.close()


@router.post("/dream-cycle", response_model=schemas.DreamCycleResponse, status_code=202)
async def trigger_dream_cycle(
    background_tasks: BackgroundTasks,
) -> schemas.DreamCycleResponse:
    """Launch the Dream Cycle background analysis worker.

    Gap 8 — Requirements 8.1/8.2:
    - Returns HTTP 202 immediately with the new job ID.
    - Returns HTTP 409 when a cycle is already running.
    """
    if _dream_cycle_state["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="A Dream Cycle is already running. Wait for it to complete.",
        )

    job_id = str(uuid.uuid4())
    _dream_cycle_state["status"] = "running"
    _dream_cycle_state["job_id"] = job_id
    _dream_cycle_state["error"] = None

    from contexta.api.config import load_api_config
    db_path = load_api_config().db_path
    background_tasks.add_task(_run_dream_cycle_task, db_path, job_id)

    logger.info("[INFO] Dream Cycle triggered — job_id=%s", job_id)
    return schemas.DreamCycleResponse(job_id=job_id, status="running")


@router.get("/dream-cycle/status", response_model=schemas.DreamCycleStatusResponse)
async def get_dream_cycle_status() -> schemas.DreamCycleStatusResponse:
    """Return the current Dream Cycle status and last completion timestamp.

    Gap 8 — Requirement 8.3: reflects module-level state set by the
    background task.  No DB access required.
    """
    return schemas.DreamCycleStatusResponse(
        status=_dream_cycle_state["status"],
        last_run=_dream_cycle_state["last_run"],
        error=_dream_cycle_state["error"],
    )


# ── Gap 9: Blueprint Management ───────────────────────────────────────────────

@router.get("/blueprints", response_model=schemas.BlueprintListResponse)
async def list_blueprints(
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.BlueprintListResponse:
    """Return all prompt blueprints with a truncated prompt preview.

    Gap 9 — Requirement 9.1: includes id, name, version_string, is_active,
    and the first 200 characters of master_prompt_text as ``prompt_preview``.
    """
    blueprints = await db_repo.list_blueprints(conn)
    return schemas.BlueprintListResponse(
        blueprints=[
            schemas.BlueprintItem(
                id=bp.id,
                name=bp.blueprint_name,
                version_string=bp.version_string,
                is_active=bp.is_active,
                prompt_preview=bp.master_prompt_text[:200],
            )
            for bp in blueprints
        ]
    )


@router.post("/blueprints", response_model=schemas.BlueprintItemResponse, status_code=201)
async def create_blueprint(
    body: schemas.CreateBlueprintRequest,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.BlueprintItemResponse:
    """Create a new prompt blueprint (inactive by default).

    Gap 9 — Requirements 9.2/Property 15: the new blueprint always has
    ``is_active = false`` and does not disturb the currently active blueprint.
    """
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Blueprint name must not be empty.")
    if not body.version_string.strip():
        raise HTTPException(
            status_code=422, detail="version_string must not be empty."
        )
    if not body.prompt_text.strip():
        raise HTTPException(status_code=422, detail="prompt_text must not be empty.")

    bp = await db_repo.save_blueprint_version(
        conn,
        name=body.name.strip(),
        version=body.version_string.strip(),
        prompt_text=body.prompt_text.strip(),
    )

    logger.info(
        "[INFO] Blueprint created — id=%s name='%s' version='%s'",
        bp.id, bp.blueprint_name, bp.version_string,
    )
    return schemas.BlueprintItemResponse(
        id=bp.id,
        name=bp.blueprint_name,
        version_string=bp.version_string,
        is_active=bp.is_active,
    )


@router.post(
    "/blueprints/{blueprint_id}/activate",
    response_model=schemas.ActivateResponse,
)
async def activate_blueprint(
    blueprint_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ActivateResponse:
    """Set one blueprint active and deactivate all others.

    Gap 9 — Requirements 9.3/9.4/Property 14: after this call exactly one
    blueprint has ``is_active = true``.  Returns HTTP 404 when the blueprint
    does not exist.
    """
    try:
        await db_repo.activate_blueprint(conn, blueprint_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    logger.info("[INFO] Blueprint '%s' activated.", blueprint_id)
    return schemas.ActivateResponse(status="activated")
