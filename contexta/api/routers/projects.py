"""
contexta/api/routers/projects.py

GET  /api/projects            — list all projects with version/review counts
DELETE /api/projects/{id}     — cascade-delete a project
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
router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=schemas.ProjectListResponse)
async def list_projects(
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ProjectListResponse:
    """Return all projects with aggregated counts and storage estimate."""
    projects = await db_repo.list_projects(conn)
    items: list[schemas.ProjectItem] = []
    for p in projects:
        stats = await api_repo.get_project_stats(conn, p.id)
        items.append(
            schemas.ProjectItem(
                project_id=p.id,
                name=p.name,
                version_count=stats["version_count"],
                review_count=stats["review_count"],
                storage_bytes=stats["storage_bytes"],
            )
        )
    return schemas.ProjectListResponse(projects=items)


@router.delete("/{project_id}", response_model=schemas.DeleteResponse)
async def delete_project(
    project_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.DeleteResponse:
    """Cascade-delete a project and all child data."""
    deleted = await api_repo.delete_project_cascade(conn, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    logger.info("Project deleted: %s", project_id)
    return schemas.DeleteResponse(id=project_id, status="deleted")
