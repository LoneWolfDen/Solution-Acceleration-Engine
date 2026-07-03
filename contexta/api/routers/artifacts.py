"""
contexta/api/routers/artifacts.py

GET    /api/projects/{project_id}/artifacts
POST   /api/artifacts
PATCH  /api/artifacts/{artifact_id}
DELETE /api/artifacts/{artifact_id}
GET    /api/artifacts/suggestions
"""

from __future__ import annotations

import json
import re
from typing import List

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from ...db import repositories as repo
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

# ── Tag suggestion rules — regex/file-type ONLY, no LLM calls ─────────────────

_EXTENSION_TAGS: dict[str, list[str]] = {
    ".md": ["markdown", "documentation"],
    ".pdf": ["pdf", "document"],
    ".docx": ["word", "document"],
    ".txt": ["text", "plain"],
    ".py": ["python", "code"],
    ".json": ["json", "data"],
    ".yaml": ["yaml", "config"],
    ".yml": ["yaml", "config"],
    ".csv": ["csv", "data"],
}

_KEYWORD_TAGS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bstatement\s+of\s+work\b", re.I), "sow"),
    (re.compile(r"\bsow\b", re.I), "sow"),
    (re.compile(r"\barchitecture\b", re.I), "architecture"),
    (re.compile(r"\brequirements?\b", re.I), "requirements"),
    (re.compile(r"\bproposal\b", re.I), "proposal"),
    (re.compile(r"\bscope\b", re.I), "scope"),
    (re.compile(r"\bresource\b", re.I), "resources"),
    (re.compile(r"\brisk\b", re.I), "risk"),
    (re.compile(r"\btimeline\b", re.I), "timeline"),
    (re.compile(r"\bbankingbank\b|\bfinancial\b|\bfinance\b", re.I), "finance"),
    (re.compile(r"\bpharma\b|\bpharmaceutical\b", re.I), "pharma"),
    (re.compile(r"\bdrone\b", re.I), "drone"),
]


def _suggest_tags(filename: str, content_preview: str) -> List[str]:
    """Return tag suggestions from filename extension and keyword analysis only."""
    suggestions: set[str] = set()

    # Extension-based tags.
    for ext, tags in _EXTENSION_TAGS.items():
        if filename.lower().endswith(ext):
            suggestions.update(tags)

    # Keyword-based tags from filename + content preview.
    combined = f"{filename} {content_preview}"
    for pattern, tag in _KEYWORD_TAGS:
        if pattern.search(combined):
            suggestions.add(tag)

    return sorted(suggestions)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/api/projects/{project_id}/artifacts", response_model=ArtifactListResponse)
async def list_artifacts(
    project_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ArtifactListResponse:
    project = await repo.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    cursor = await db.execute(
        "SELECT id, node_name, metadata_json, created_at FROM nodes "
        "WHERE project_id = ? AND layer_type = 'exploration' ORDER BY created_at",
        (project_id,),
    )
    rows = await cursor.fetchall()

    artifacts: list[ArtifactSummary] = []
    for row in rows:
        meta = json.loads(row["metadata_json"] or "{}")
        artifacts.append(
            ArtifactSummary(
                artifact_id=row["id"],
                title=row["node_name"],
                tags=meta.get("tags", []),
                is_active=bool(meta.get("is_active", True)),
                created_at=row["created_at"],
            )
        )
    return ArtifactListResponse(artifacts=artifacts, error=None)


@router.post("/api/artifacts", response_model=ArtifactCreateResponse, status_code=201)
async def create_artifact(
    body: ArtifactCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> ArtifactCreateResponse:
    if body.source not in ("upload", "paste", "url"):
        raise HTTPException(
            status_code=422,
            detail="source must be 'upload', 'paste', or 'url'.",
        )
    if body.source == "url" and not body.url:
        raise HTTPException(
            status_code=422,
            detail="url is required when source='url'.",
        )
    if body.source == "paste" and not body.content:
        raise HTTPException(
            status_code=422,
            detail="content is required when source='paste'.",
        )
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="title must not be empty.")

    project = await repo.get_project(db, body.project_id)
    if project is None:
        raise HTTPException(
            status_code=404, detail=f"Project '{body.project_id}' not found."
        )

    from datetime import datetime, timezone

    import uuid

    node_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    meta = {
        "tags": body.tags,
        "is_active": True,
        "source": body.source,
        "url": body.url,
    }
    content = body.content or body.url or ""

    await db.execute(
        """
        INSERT INTO nodes
            (id, project_id, parent_id, layer_type, node_name,
             metadata_json, content_markdown, created_at, version_tag, version_id)
        VALUES (?, ?, NULL, 'exploration', ?, ?, ?, ?, NULL, NULL)
        """,
        (node_id, body.project_id, body.title, json.dumps(meta), content, now),
    )
    await db.commit()

    return ArtifactCreateResponse(
        artifact_id=node_id,
        title=body.title,
        tags=body.tags,
        is_active=True,
        created_at=now,
        error=None,
    )


@router.patch("/api/artifacts/{artifact_id}", response_model=ArtifactPatchResponse)
async def patch_artifact(
    artifact_id: str,
    body: ArtifactPatchRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> ArtifactPatchResponse:
    cursor = await db.execute(
        "SELECT id, metadata_json FROM nodes WHERE id = ? AND layer_type = 'exploration'",
        (artifact_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Artifact '{artifact_id}' not found."
        )

    meta = json.loads(row["metadata_json"] or "{}")
    meta["is_active"] = body.active
    await db.execute(
        "UPDATE nodes SET metadata_json = ? WHERE id = ?",
        (json.dumps(meta), artifact_id),
    )
    await db.commit()

    return ArtifactPatchResponse(
        artifact_id=artifact_id,
        is_active=body.active,
        error=None,
    )


@router.delete("/api/artifacts/{artifact_id}", response_model=ArtifactDeleteResponse)
async def delete_artifact(
    artifact_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ArtifactDeleteResponse:
    cursor = await db.execute(
        "SELECT id FROM nodes WHERE id = ? AND layer_type = 'exploration'",
        (artifact_id,),
    )
    if await cursor.fetchone() is None:
        raise HTTPException(
            status_code=404, detail=f"Artifact '{artifact_id}' not found."
        )

    await db.execute("DELETE FROM nodes WHERE id = ?", (artifact_id,))
    await db.commit()

    return ArtifactDeleteResponse(artifact_id=artifact_id, status="deleted", error=None)


@router.get("/api/artifacts/suggestions", response_model=ArtifactSuggestionsResponse)
async def get_suggestions(
    filename: str = Query(default=""),
    content_preview: str = Query(default=""),
) -> ArtifactSuggestionsResponse:
    suggestions = _suggest_tags(filename, content_preview)
    return ArtifactSuggestionsResponse(suggestions=suggestions, error=None)
