"""GET /api/projects and DELETE /api/projects/{project_id}."""

from __future__ import annotations

import json

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_db
from ..schemas import (
    ProjectDeleteResponse,
    ProjectListResponse,
    ProjectSummary,
)

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(db: aiosqlite.Connection = Depends(get_db)) -> ProjectListResponse:
    """Return all projects with version_count, review_count, and storage_bytes."""
    cursor = await db.execute(
        """
        SELECT
            p.id,
            p.name,
            (SELECT COUNT(*) FROM versions v WHERE v.project_id = p.id)  AS version_count,
            (SELECT COUNT(*) FROM reviews  r
             JOIN versions v2 ON r.version_id = v2.id
             WHERE v2.project_id = p.id)                                  AS review_count,
            (SELECT COALESCE(SUM(LENGTH(n.content_markdown)), 0)
             FROM nodes n WHERE n.project_id = p.id)                      AS storage_bytes
        FROM projects p
        ORDER BY p.rowid
        """
    )
    rows = await cursor.fetchall()
    projects = [
        ProjectSummary(
            project_id=row["id"],
            name=row["name"],
            version_count=row["version_count"],
            review_count=row["review_count"],
            storage_bytes=row["storage_bytes"],
        )
        for row in rows
    ]
    return ProjectListResponse(projects=projects, error=None)


@router.delete("/projects/{project_id}", response_model=ProjectDeleteResponse)
async def delete_project(
    project_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ProjectDeleteResponse:
    """Delete a project and all its child records (cascade)."""
    cursor = await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")

    # Cascade manually (SQLite FK cascade requires ON DELETE CASCADE in DDL;
    # we delete in dependency order to avoid FK violations even if CASCADE is
    # not active on the running DB file).
    await db.execute(
        """
        DELETE FROM proposals
        WHERE review_id IN (
            SELECT r.id FROM reviews r
            JOIN versions v ON r.version_id = v.id
            WHERE v.project_id = ?
        )
        """,
        (project_id,),
    )
    await db.execute(
        """
        DELETE FROM reviews
        WHERE version_id IN (SELECT id FROM versions WHERE project_id = ?)
        """,
        (project_id,),
    )
    await db.execute(
        """
        DELETE FROM version_artifacts
        WHERE version_id IN (SELECT id FROM versions WHERE project_id = ?)
        """,
        (project_id,),
    )
    await db.execute("DELETE FROM versions WHERE project_id = ?", (project_id,))
    await db.execute("DELETE FROM artifacts WHERE project_id = ?", (project_id,))
    await db.execute(
        "DELETE FROM nodes WHERE project_id = ?",
        (project_id,),
    )
    await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    await db.commit()

    return ProjectDeleteResponse(project_id=project_id, status="deleted", error=None)
