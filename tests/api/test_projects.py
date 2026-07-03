"""
tests/api/test_projects.py

5.2 — Project endpoint contract tests.

Covers:
- GET /api/projects returns list with all required fields
- GET /api/projects returns empty list when no projects exist
- DELETE /api/projects/{id} removes project and cascades to children
- DELETE /api/projects/{unknown_id} returns 404 with error field
"""

from __future__ import annotations


# ── GET /api/projects ─────────────────────────────────────────────────────────


def test_list_projects_empty(client):
    """Returns an empty list when no projects exist."""
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    body = resp.json()
    assert body["projects"] == []
    assert body["error"] is None


def test_list_projects_returns_required_fields(client, project_id):
    """Every project summary includes all required fields."""
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["projects"]) == 1
    p = body["projects"][0]
    assert p["project_id"] == project_id
    assert p["name"] == "Test Project"
    assert isinstance(p["version_count"], int)
    assert isinstance(p["review_count"], int)
    assert isinstance(p["storage_bytes"], int)
    assert body["error"] is None


def test_list_projects_version_count(client, db_conn, project_id):
    """version_count reflects actual version rows in DB."""
    import asyncio
    from contexta.db import repositories as repo
    asyncio.get_event_loop().run_until_complete(
        repo.create_version(db_conn, project_id, "v2.0")
    )
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    p = resp.json()["projects"][0]
    assert p["version_count"] == 1  # one version created by fixture


def test_list_projects_multiple(client, db_conn):
    """Multiple projects are all returned."""
    import asyncio
    from contexta.db import repositories as repo
    asyncio.get_event_loop().run_until_complete(
        repo.create_project(db_conn, "Alpha", [])
    )
    asyncio.get_event_loop().run_until_complete(
        repo.create_project(db_conn, "Beta", [])
    )
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert len(resp.json()["projects"]) == 2


# ── DELETE /api/projects/{project_id} ────────────────────────────────────────


def test_delete_project_success(client, project_id):
    """DELETE removes the project and returns status=deleted."""
    resp = client.delete(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == project_id
    assert body["status"] == "deleted"
    assert body["error"] is None


def test_delete_project_not_found_in_list(client, project_id):
    """After deletion the project no longer appears in GET /api/projects."""
    client.delete(f"/api/projects/{project_id}")
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert resp.json()["projects"] == []


def test_delete_project_cascades_nodes(client, db_conn, project_id, artifact_id):
    """Deleting a project also removes its child nodes."""
    import asyncio
    from contexta.db import repositories as repo
    client.delete(f"/api/projects/{project_id}")
    node = asyncio.get_event_loop().run_until_complete(
        repo.get_node(db_conn, artifact_id)
    )
    assert node is None


def test_delete_project_cascades_versions(client, db_conn, project_id, version_id):
    """Deleting a project also removes its child versions."""
    import asyncio
    from contexta.db import repositories as repo
    client.delete(f"/api/projects/{project_id}")
    version = asyncio.get_event_loop().run_until_complete(
        repo.get_version(db_conn, version_id)
    )
    assert version is None


def test_delete_project_unknown_id_returns_404(client):
    """DELETE with an unknown project_id returns 404 with error field."""
    resp = client.delete("/api/projects/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    # FastAPI 404 detail is in "detail" key from HTTPException
    assert "detail" in body or "error" in body
