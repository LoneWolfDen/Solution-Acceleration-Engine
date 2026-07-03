"""Artifact CRUD: GET/POST/PATCH/DELETE + tag suggestions."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_db
from ..schemas import (
    ArtifactCreateRequest,
    ArtifactCreateResponse,
    ArtifactDeleteResponse,
    ArtifactListResponse,
    ArtifactPatchRequest,
    ArtifactPatchResponse,
    ArtifactSuggestionsResponse,
    ArtifactSummary,
)

router = APIRouter(tags=["artifacts"])

# ── Suggestion rules (regex / file-type only — zero LLM calls) ───────────────

_TAG_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"architecture|arch|design", re.I), "architecture"),
    (re.compile(r"scope|sow|statement.of.work", re.I), "scope"),
    (re.compile(r"requirement|nfr|non.functional", re.I), "requirements"),
    (re.compile(r"resource|team|staffing|personnel", re.I), "resources"),
    (re.compile(r"risk|risk.register|assumption", re.I), "risk"),
    (re.compile(r"timeline|schedule|milestone|gantt", re.I), "timeline"),
    (re.compile(r"commercial|contract|pricing|budget", re.I), "commercial"),
    (re.compile(r"technical|tech.spec|api.spec", re.I), "technical"),
    (re.compile(r"proposal|rfp|rfq|tender", re.I), "proposal"),
    (re.compile(r"delivery|deployment|release|launch", re.I), "delivery"),
    (re.compile(r"security|auth|access.control|iam", re.I), "security"),
    (re.compile(r"infrastructure|infra|cloud|aws|azure|gcp", re.I), "infrastructure"),
]


def _suggest_tags(filename: str, content_preview: str) -> list[str]:
    """Return tag suggestions based purely on filename and content regex patterns."""
    combined = f"{filename} {content_preview}"
    seen: set[str] = set()
    result: list[str] = []
    for pattern, tag in _TAG_RULES:
        if pattern.search(combined) and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/artifacts", response_model=ArtifactListResponse)
async def list_artifacts(
    project_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ArtifactListResponse:
    """Return all artifacts for a project with explicit is_active field."""
    cursor = await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    cursor = await db.execute(
        "SELECT id, title, tags, is_active, created_at FROM artifacts WHERE project_id = ? ORDER BY created_at",
        (project_id,),
    )
    rows = await cursor.fetchall()
    artifacts = [
        ArtifactSummary(
            artifact_id=row["id"],
            title=row["title"],
            tags=json.loads(row["tags"] or "[]"),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return ArtifactListResponse(artifacts=artifacts, error=None)


@router.post("/artifacts", response_model=ArtifactCreateResponse, status_code=201)
async def create_artifact(
    body: ArtifactCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> ArtifactCreateResponse:
    """Ingest a new artifact into a project."""
    if body.source not in ("upload", "paste", "url"):
        raise HTTPException(
            status_code=422,
            detail="source must be one of: upload, paste, url.",
        )

    cursor = await db.execute("SELECT id FROM projects WHERE id = ?", (body.project_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{body.project_id}' not found.",
        )

    if body.source == "url" and not body.url:
        raise HTTPException(status_code=422, detail="url is required when source='url'.")
    if body.source == "paste" and body.content is None:
        raise HTTPException(
            status_code=422, detail="content is required when source='paste'."
        )

    artifact_id = _new_id()
    now = _now_iso()
    content = body.content or ""

    await db.execute(
        """
        INSERT INTO artifacts (id, project_id, title, source, content, url, tags, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            artifact_id,
            body.project_id,
            body.title,
            body.source,
            content,
            body.url,
            json.dumps(body.tags),
            now,
        ),
    )
    await db.commit()

    return ArtifactCreateResponse(
        artifact_id=artifact_id,
        title=body.title,
        tags=body.tags,
        is_active=True,
        created_at=now,
        error=None,
    )


@router.patch("/artifacts/{artifact_id}", response_model=ArtifactPatchResponse)
async def patch_artifact(
    artifact_id: str,
    body: ArtifactPatchRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> ArtifactPatchResponse:
    """Toggle the is_active flag on an artifact."""
    cursor = await db.execute("SELECT id FROM artifacts WHERE id = ?", (artifact_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found.")

    await db.execute(
        "UPDATE artifacts SET is_active = ? WHERE id = ?",
        (1 if body.active else 0, artifact_id),
    )
    await db.commit()

    return ArtifactPatchResponse(
        artifact_id=artifact_id,
        is_active=body.active,
        error=None,
    )


@router.delete("/artifacts/{artifact_id}", response_model=ArtifactDeleteResponse)
async def delete_artifact(
    artifact_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ArtifactDeleteResponse:
    """Delete an artifact and remove it from any version-artifact joins."""
    cursor = await db.execute("SELECT id FROM artifacts WHERE id = ?", (artifact_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found.")

    await db.execute(
        "DELETE FROM version_artifacts WHERE artifact_id = ?", (artifact_id,)
    )
    await db.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
    await db.commit()

    return ArtifactDeleteResponse(artifact_id=artifact_id, status="deleted", error=None)


@router.get("/artifacts/suggestions", response_model=ArtifactSuggestionsResponse)
async def get_suggestions(
    filename: str = "",
    content_preview: str = "",
) -> ArtifactSuggestionsResponse:
    """Return tag suggestions from regex/file-type analysis only — zero LLM calls."""
    suggestions = _suggest_tags(filename, content_preview)
    return ArtifactSuggestionsResponse(suggestions=suggestions, error=None)
