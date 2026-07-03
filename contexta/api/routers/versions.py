"""GET /api/projects/{project_id}/versions, GET /api/versions/{id}, POST /api/versions."""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ..dependencies import get_db
from ..schemas import (
    ArtifactSummary,
    VersionCreateRequest,
    VersionCreateResponse,
    VersionDetailResponse,
    VersionListResponse,
    VersionSummary,
)
from ...db.repositories import create_version

router = APIRouter(tags=["versions"])


@router.get(
    "/projects/{project_id}/versions",
    response_model=VersionListResponse,
)
async def list_versions(
    project_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> VersionListResponse:
    """Return all versions for a project with artifact_count and review_count."""
    cursor = await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    cursor = await db.execute(
        """
        SELECT
            v.id,
            v.name,
            v.created_at,
            (SELECT COUNT(*) FROM version_artifacts va WHERE va.version_id = v.id) AS artifact_count,
            (SELECT COUNT(*) FROM reviews r WHERE r.version_id = v.id)             AS review_count
        FROM versions v
        WHERE v.project_id = ?
        ORDER BY v.created_at
        """,
        (project_id,),
    )
    rows = await cursor.fetchall()
    versions = [
        VersionSummary(
            version_id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            artifact_count=row["artifact_count"],
            review_count=row["review_count"],
        )
        for row in rows
    ]
    return VersionListResponse(versions=versions, error=None)


@router.get("/versions/{version_id}", response_model=VersionDetailResponse)
async def get_version(
    version_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> VersionDetailResponse:
    """Return version detail including its pinned artifacts."""
    cursor = await db.execute(
        "SELECT id, name, created_at FROM versions WHERE id = ?",
        (version_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")

    cursor = await db.execute(
        """
        SELECT a.id, a.title, a.tags, a.is_active, a.created_at
        FROM artifacts a
        JOIN version_artifacts va ON va.artifact_id = a.id
        WHERE va.version_id = ?
        ORDER BY a.created_at
        """,
        (version_id,),
    )
    artifact_rows = await cursor.fetchall()

    import json

    artifacts = [
        ArtifactSummary(
            artifact_id=ar["id"],
            title=ar["title"],
            tags=json.loads(ar["tags"] or "[]"),
            is_active=bool(ar["is_active"]),
            created_at=ar["created_at"],
        )
        for ar in artifact_rows
    ]

    return VersionDetailResponse(
        version_id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        artifacts=artifacts,
        error=None,
    )


@router.post("/versions", response_model=VersionCreateResponse, status_code=201)
async def create_version_endpoint(
    body: VersionCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> VersionCreateResponse:
    """Create a new version pinning a set of artifact_ids."""
    if not body.artifact_ids:
        raise HTTPException(
            status_code=422,
            detail="artifact_ids must contain at least one artifact.",
        )

    cursor = await db.execute("SELECT id FROM projects WHERE id = ?", (body.project_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{body.project_id}' not found.",
        )

    # Validate all artifact_ids exist and belong to the project.
    for aid in body.artifact_ids:
        cursor = await db.execute(
            "SELECT id FROM artifacts WHERE id = ? AND project_id = ?",
            (aid, body.project_id),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=422,
                detail=f"Artifact '{aid}' not found in project '{body.project_id}'.",
            )

    version_row = await create_version(db, body.project_id, body.version_name)

    # Pin artifacts.
    for aid in body.artifact_ids:
        await db.execute(
            "INSERT INTO version_artifacts (version_id, artifact_id) VALUES (?, ?)",
            (version_row.id, aid),
        )
    await db.commit()

    return VersionCreateResponse(
        version_id=version_row.id,
        name=version_row.name,
        created_at=version_row.created_at,
        artifact_count=len(body.artifact_ids),
        error=None,
    )
