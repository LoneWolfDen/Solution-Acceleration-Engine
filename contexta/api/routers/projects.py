"""
contexta/api/routers/projects.py

GET  /api/projects
DELETE /api/projects/{project_id}
"""

from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from ...db import repositories as repo
from ..dependencies import get_db
from ..schemas import ProjectDeleteResponse, ProjectListResponse, ProjectSummary

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
async def list_projects(db: aiosqlite.Connection = Depends(get_db)) -> ProjectListResponse:
    projects = await repo.list_projects(db)

    summaries: list[ProjectSummary] = []
    for p in projects:
        versions = await repo.list_versions_for_project(db, p.id)
        nodes = await repo.list_nodes_for_project(db, p.id)
        review_count = sum(
            1 for n in nodes if n.layer_type in ("exploration", "synthesis")
        )
        summaries.append(
            ProjectSummary(
                project_id=p.id,
                name=p.name,
                version_count=len(versions),
                review_count=review_count,
                storage_bytes=0,  # not tracked at DB level
            )
        )
    return ProjectListResponse(projects=summaries, error=None)


@router.delete("/{project_id}", response_model=ProjectDeleteResponse)
async def delete_project(
    project_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ProjectDeleteResponse:
    project = await repo.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    # Cascade: delete nodes, versions, then project (FK constraints enforced by SQLite).
    await db.execute("DELETE FROM nodes WHERE project_id = ?", (project_id,))
    await db.execute("DELETE FROM versions WHERE project_id = ?", (project_id,))
    await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    await db.commit()

    return ProjectDeleteResponse(project_id=project_id, status="deleted", error=None)
