"""
contexta/api/routers/artifacts.py

GET    /api/projects/{project_id}/artifacts  — list artifacts (with is_active)
POST   /api/artifacts                        — ingest upload / paste / url
PATCH  /api/artifacts/{id}                   — toggle is_active
DELETE /api/artifacts/{id}                   — hard delete
GET    /api/artifacts/suggestions            — regex-based tag hints (no LLM)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from contexta.api import repositories as api_repo
from contexta.api import schemas
from contexta.api.dependencies import get_db
from contexta.db import repositories as db_repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["artifacts"])

# ─── Tag suggestion rules (regex-based, zero LLM) ────────────────────────────

_EXTENSION_TAGS: dict[str, str] = {
    ".md": "markdown", ".txt": "text", ".pdf": "pdf",
    ".docx": "word", ".xlsx": "spreadsheet", ".csv": "csv",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml",
}

_CONTENT_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)\bstatement\s+of\s+work\b|\bsow\b", "sow"),
    (r"(?i)\barchitecture\b", "architecture"),
    (r"(?i)\brequirements?\b", "requirements"),
    (r"(?i)\brisk\b", "risk"),
    (r"(?i)\bproposal\b", "proposal"),
    (r"(?i)\bresource\s+plan\b", "resource-plan"),
    (r"(?i)\bnon-functional\b|\bnfr\b", "nfr"),
    (r"(?i)\btimeline\b|\bschedule\b", "timeline"),
    (r"(?i)\bbudget\b|\bcost\b", "budget"),
    (r"(?i)\bscope\b", "scope"),
    (r"(?i)\bdelivery\b|\bdeliverable\b", "delivery"),
    (r"(?i)\bsecurity\b", "security"),
    (r"(?i)\bcompliance\b|\bregulat", "compliance"),
    (r"(?i)\binfrastructure\b|\bcloud\b", "infrastructure"),
]


def _derive_suggestions(filename: str, content_preview: str) -> list[str]:
    """Return deduplicated tag suggestions from filename extension and content."""
    seen: set[str] = set()
    tags: list[str] = []

    _, ext = os.path.splitext(filename.lower())
    if ext in _EXTENSION_TAGS:
        tag = _EXTENSION_TAGS[ext]
        seen.add(tag)
        tags.append(tag)

    for pattern, tag in _CONTENT_PATTERNS:
        if tag not in seen and re.search(pattern, content_preview[:500]):
            seen.add(tag)
            tags.append(tag)

    return tags


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get(
    "/projects/{project_id}/artifacts",
    response_model=schemas.ArtifactListResponse,
)
async def list_artifacts(
    project_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ArtifactListResponse:
    """Return all artifacts for a project.  is_active is explicit on every item."""
    project = await db_repo.get_project(conn, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    artifacts = await api_repo.list_artifacts_for_project(conn, project_id)
    return schemas.ArtifactListResponse(
        artifacts=[
            schemas.ArtifactItem(
                artifact_id=a.id,
                title=a.title,
                tags=a.tags,
                is_active=a.is_active,
                created_at=a.created_at,
                line_count=a.line_count,
                content_preview=a.content_preview,
            )
            for a in artifacts
        ]
    )


@router.post("/artifacts", response_model=schemas.ArtifactResponse, status_code=201)
async def create_artifact(
    project_id: str = Form(...),
    title: str = Form(...),
    source: str = Form(...),
    content: str = Form(""),
    url: str = Form(""),
    tags: str = Form("[]"),           # JSON-encoded string array
    file: Optional[UploadFile] = File(None),
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ArtifactResponse:
    """Ingest an artifact via file upload, pasted text, or URL reference."""
    import json as _json

    valid_sources = {"upload", "paste", "url"}
    if source not in valid_sources:
        raise HTTPException(
            status_code=422, detail=f"source must be one of {sorted(valid_sources)}."
        )

    project = await db_repo.get_project(conn, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    try:
        tag_list: list[str] = _json.loads(tags)
        if not isinstance(tag_list, list):
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="tags must be a JSON array of strings.")

    body_content = content
    filename: Optional[str] = None
    source_url: Optional[str] = None

    if source == "upload":
        if file is None:
            raise HTTPException(status_code=422, detail="A file must be provided for source='upload'.")
        raw = await file.read()
        body_content = raw.decode("utf-8", errors="replace")
        filename = file.filename
    elif source == "url":
        if not url:
            raise HTTPException(status_code=422, detail="url must be provided for source='url'.")
        source_url = url
    elif source == "paste":
        if not content:
            raise HTTPException(status_code=422, detail="content must be provided for source='paste'.")

    artifact = await api_repo.create_artifact(
        conn,
        project_id=project_id,
        title=title,
        content=body_content,
        source=source,
        tags=tag_list,
        source_url=source_url,
        filename=filename,
    )
    logger.info("Artifact created: %s (%s) source=%s", artifact.title, artifact.id, source)
    return schemas.ArtifactResponse(
        artifact_id=artifact.id,
        title=artifact.title,
        tags=artifact.tags,
        is_active=artifact.is_active,
        created_at=artifact.created_at,
        line_count=artifact.line_count,
        content_preview=artifact.content_preview,
    )


@router.patch("/artifacts/{artifact_id}", response_model=schemas.ArtifactResponse)
async def update_artifact_active(
    artifact_id: str,
    body: schemas.UpdateArtifactRequest,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ArtifactResponse:
    """Toggle the is_active flag for triage."""
    updated = await api_repo.update_artifact_active(conn, artifact_id, body.active)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found.")
    return schemas.ArtifactResponse(
        artifact_id=updated.id,
        title=updated.title,
        tags=updated.tags,
        is_active=updated.is_active,
        created_at=updated.created_at,
        line_count=updated.line_count,
        content_preview=updated.content_preview,
    )


@router.delete("/artifacts/{artifact_id}", response_model=schemas.DeleteResponse)
async def delete_artifact(
    artifact_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.DeleteResponse:
    deleted = await api_repo.delete_artifact(conn, artifact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found.")
    logger.info("Artifact deleted: %s", artifact_id)
    return schemas.DeleteResponse(id=artifact_id, status="deleted")


@router.get("/artifacts/suggestions", response_model=schemas.SuggestionsResponse)
async def get_suggestions(
    filename: str = "",
    content_preview: str = "",
) -> schemas.SuggestionsResponse:
    """Return regex-derived tag hints.  No LLM calls are made."""
    return schemas.SuggestionsResponse(
        suggestions=_derive_suggestions(filename, content_preview)
    )
