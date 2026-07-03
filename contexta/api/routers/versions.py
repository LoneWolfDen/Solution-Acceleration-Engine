"""
contexta/api/routers/versions.py

GET  /api/projects/{project_id}/versions  — list versions for a project
GET  /api/versions/{version_id}           — version detail + linked artifacts
POST /api/versions                        — create version and link artifacts
"""

from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from contexta.api import repositories as api_repo
from contexta.api import schemas
from contexta.api.dependencies import get_db
from contexta.db import repositories as db_repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["versions"])


@router.get(
    "/projects/{project_id}/versions",
    response_model=schemas.VersionListResponse,
)
async def list_versions(
    project_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.VersionListResponse:
    """Return all versions for a project, with artifact and review counts."""
    project = await db_repo.get_project(conn, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    versions = await db_repo.list_versions_for_project(conn, project_id)
    items: list[schemas.VersionItem] = []
    for v in versions:
        artifacts = await api_repo.list_artifacts_for_version(conn, v.id)
        jobs = await api_repo.list_review_jobs_for_version(conn, v.id)
        items.append(
            schemas.VersionItem(
                version_id=v.id,
                name=v.name,
                created_at=v.created_at,
                artifact_count=len(artifacts),
                review_count=len(jobs),
            )
        )
    return schemas.VersionListResponse(versions=items)


@router.get("/versions/{version_id}", response_model=schemas.VersionDetailResponse)
async def get_version(
    version_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.VersionDetailResponse:
    """Return version detail including all linked artifacts with is_active state."""
    version = await db_repo.get_version(conn, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")

    artifacts = await api_repo.list_artifacts_for_version(conn, version_id)
    artifact_items = [
        schemas.ArtifactInVersion(
            artifact_id=a.id,
            title=a.title,
            tags=a.tags,
            is_active=a.is_active,
        )
        for a in artifacts
    ]
    return schemas.VersionDetailResponse(
        version_id=version.id,
        name=version.name,
        created_at=version.created_at,
        artifacts=artifact_items,
    )


@router.post("/versions", response_model=schemas.CreateVersionResponse, status_code=201)
async def create_version(
    body: schemas.CreateVersionRequest,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.CreateVersionResponse:
    """Create a new version and link the supplied artifact IDs to it."""
    if not body.artifact_ids:
        raise HTTPException(
            status_code=422,
            detail="artifact_ids must contain at least one artifact.",
        )

    project = await db_repo.get_project(conn, body.project_id)
    if project is None:
        raise HTTPException(
            status_code=404, detail=f"Project '{body.project_id}' not found."
        )

    version = await db_repo.create_version(conn, body.project_id, body.version_name)
    await api_repo.link_artifacts_to_version(conn, version.id, body.artifact_ids)

    logger.info(
        "Version created: %s (%s) with %d artifacts",
        version.name, version.id, len(body.artifact_ids),
    )
    return schemas.CreateVersionResponse(
        version_id=version.id,
        name=version.name,
        created_at=version.created_at,
        artifact_count=len(body.artifact_ids),
    )
