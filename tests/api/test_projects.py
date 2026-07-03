"""Milestone 5.2 — tests/api/test_projects.py

Tests:
  - GET /api/projects returns list with all required fields
  - GET /api/projects returns empty list when no projects exist
  - DELETE /api/projects/{id} removes project and cascades to children
  - DELETE /api/projects/{unknown_id} returns 404 with error field
"""

from __future__ import annotations

import pytest

from .conftest import seed_artifact, seed_project, seed_review, seed_version


@pytest.mark.asyncio
async def test_list_projects_empty(client, mem_db):
    """Empty DB returns an empty list with error: null."""
    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    body = resp.json()
    assert body["projects"] == []
    assert body["error"] is None


@pytest.mark.asyncio
async def test_list_projects_returns_required_fields(client, mem_db):
    """Each project entry contains all contract-required fields."""
    pid = await seed_project(mem_db, "Alpha Project")

    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["projects"]) == 1

    proj = body["projects"][0]
    assert proj["project_id"] == pid
    assert proj["name"] == "Alpha Project"
    assert isinstance(proj["version_count"], int)
    assert isinstance(proj["review_count"], int)
    assert isinstance(proj["storage_bytes"], int)
    assert body["error"] is None


@pytest.mark.asyncio
async def test_list_projects_version_and_review_counts(client, mem_db):
    """version_count and review_count are accurate."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid])
    await seed_review(mem_db, vid)

    resp = await client.get("/api/projects")
    proj = resp.json()["projects"][0]
    assert proj["version_count"] == 1
    assert proj["review_count"] == 1


@pytest.mark.asyncio
async def test_delete_project_removes_project(client, mem_db):
    """DELETE returns status=deleted and the project no longer appears in list."""
    pid = await seed_project(mem_db)

    resp = await client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == pid
    assert body["status"] == "deleted"
    assert body["error"] is None

    list_resp = await client.get("/api/projects")
    assert list_resp.json()["projects"] == []


@pytest.mark.asyncio
async def test_delete_project_cascades_to_children(client, mem_db):
    """Deleting a project also removes its versions, artifacts, and reviews."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid])
    rid = await seed_review(mem_db, vid)

    resp = await client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 200

    # Verify cascade: version and review rows gone.
    cursor = await mem_db.execute("SELECT id FROM versions WHERE id = ?", (vid,))
    assert await cursor.fetchone() is None

    cursor = await mem_db.execute("SELECT id FROM reviews WHERE id = ?", (rid,))
    assert await cursor.fetchone() is None

    cursor = await mem_db.execute("SELECT id FROM artifacts WHERE id = ?", (aid,))
    assert await cursor.fetchone() is None


@pytest.mark.asyncio
async def test_delete_project_unknown_id_returns_404(client, mem_db):
    """404 response includes a non-null error field."""
    resp = await client.delete("/api/projects/nonexistent-id")
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body or "detail" in body
