"""
contexta/api/routers/versions.py

GET  /api/projects/{project_id}/versions
GET  /api/versions/{version_id}
POST /api/versions
"""

from __future__ import annotations

import json

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from ...db import repositories as repo
from ..dependencies import get_db
from ..schemas import (
    ArtifactInVersion,
    VersionCreateRequest,
    VersionCreateResponse,
    VersionDetailResponse,
    VersionListResponse,
    VersionSummary,
)

router = APIRouter(tags=["versions"])


@router.get("/api/projects/{project_id}/versions", response_model=VersionListResponse)
async def list_versions(
    project_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> VersionListResponse:
    project = await repo.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    versions = await repo.list_versions_for_project(db, project_id)
    all_nodes = await repo.list_nodes_for_project(db, project_id)

    summaries: list[VersionSummary] = []
    for v in versions:
        artifacts = [
            n for n in all_nodes
            if n.version_id == v.id and n.layer_type == "exploration"
        ]
        reviews = [
            n for n in all_nodes
            if n.version_id == v.id and n.layer_type in ("synthesis",)
        ]
        summaries.append(
            VersionSummary(
                version_id=v.id,
                name=v.name,
                created_at=v.created_at,
                artifact_count=len(artifacts),
                review_count=len(reviews),
            )
        )
    return VersionListResponse(versions=summaries, error=None)


@router.get("/api/versions/{version_id}", response_model=VersionDetailResponse)
async def get_version(
    version_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> VersionDetailResponse:
    version = await repo.get_version(db, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")

    # Artifacts are exploration nodes belonging to this version.
    cursor = await db.execute(
        "SELECT id, node_name, metadata_json, created_at FROM nodes "
        "WHERE version_id = ? AND layer_type = 'exploration'",
        (version_id,),
    )
    rows = await cursor.fetchall()

    artifacts: list[ArtifactInVersion] = []
    for row in rows:
        meta = json.loads(row["metadata_json"] or "{}")
        tags = meta.get("tags", [])
        is_active = meta.get("is_active", True)
        artifacts.append(
            ArtifactInVersion(
                artifact_id=row["id"],
                title=row["node_name"],
                tags=tags,
                is_active=bool(is_active),
            )
        )

    return VersionDetailResponse(
        version_id=version.id,
        name=version.name,
        created_at=version.created_at,
        artifacts=artifacts,
        error=None,
    )


@router.post("/api/versions", response_model=VersionCreateResponse, status_code=201)
async def create_version(
    body: VersionCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> VersionCreateResponse:
    if not body.artifact_ids:
        raise HTTPException(
            status_code=422,
            detail="artifact_ids must contain at least one artifact ID.",
        )

    project = await repo.get_project(db, body.project_id)
    if project is None:
        raise HTTPException(
            status_code=404, detail=f"Project '{body.project_id}' not found."
        )

    # Validate all artifact IDs exist as exploration nodes.
    for art_id in body.artifact_ids:
        cursor = await db.execute(
            "SELECT id FROM nodes WHERE id = ? AND layer_type = 'exploration'",
            (art_id,),
        )
        if await cursor.fetchone() is None:
            raise HTTPException(
                status_code=422,
                detail=f"Artifact '{art_id}' not found or is not an exploration node.",
            )

    version = await repo.create_version(db, body.project_id, body.version_name)

    # Associate all artifact nodes with this new version.
    for art_id in body.artifact_ids:
        await db.execute(
            "UPDATE nodes SET version_id = ? WHERE id = ?",
            (version.id, art_id),
        )
    await db.commit()

    return VersionCreateResponse(
        version_id=version.id,
        name=version.name,
        created_at=version.created_at,
        artifact_count=len(body.artifact_ids),
        error=None,
    )
