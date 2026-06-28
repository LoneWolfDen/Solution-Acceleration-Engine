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


@router.get("/{project_id}", tags=["projects"])
async def get_project_detail(
    project_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """Return a project with its versions and node summaries (for sidebar expansion)."""
    from contexta.api.schemas import VersionResponse, NodeSummaryResponse, ProjectDetailResponse
    project = await db_repo.get_project(conn, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    versions = await db_repo.list_versions_for_project(conn, project_id)
    nodes = await db_repo.list_nodes_for_project(conn, project_id)

    return {
        "id": project.id,
        "name": project.name,
        "global_tags": project.global_tags,
        "versions": [
            {"id": v.id, "project_id": v.project_id, "name": v.name,
             "description": v.description, "created_at": v.created_at}
            for v in versions
        ],
        "nodes": [
            {"id": n.id, "project_id": n.project_id, "parent_id": n.parent_id,
             "layer_type": n.layer_type, "node_name": n.node_name,
             "created_at": n.created_at, "version_tag": n.version_tag,
             "version_id": n.version_id}
            for n in nodes
        ],
        "error": None,
    }


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
