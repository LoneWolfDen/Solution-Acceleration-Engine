"""Milestone 5.4 — tests/api/test_versions.py

Tests:
  - POST /api/versions creates version with correct artifact_ids
  - GET /api/versions/{id} returns artifacts with is_active field
  - POST /api/versions with empty artifact_ids returns 422 with error field
  - GET /api/projects/{id}/versions returns version list
"""

from __future__ import annotations

import pytest

from .conftest import seed_artifact, seed_project, seed_version


@pytest.mark.asyncio
async def test_create_version_success(client, mem_db):
    """POST /api/versions creates a version pinning the given artifact_ids."""
    pid = await seed_project(mem_db)
    aid1 = await seed_artifact(mem_db, pid, "Doc 1")
    aid2 = await seed_artifact(mem_db, pid, "Doc 2")

    resp = await client.post(
        "/api/versions",
        json={
            "project_id": pid,
            "version_name": "v1.0",
            "artifact_ids": [aid1, aid2],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["name"] == "v1.0"
    assert body["artifact_count"] == 2
    assert "version_id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_version_empty_artifact_ids_returns_422(client, mem_db):
    """POST /api/versions with empty artifact_ids must return 422."""
    pid = await seed_project(mem_db)

    resp = await client.post(
        "/api/versions",
        json={
            "project_id": pid,
            "version_name": "v1.0",
            "artifact_ids": [],
        },
    )
    assert resp.status_code == 422
    # error information must be present
    body = resp.json()
    assert "detail" in body or "error" in body


@pytest.mark.asyncio
async def test_create_version_unknown_project_returns_404(client, mem_db):
    """POST /api/versions with unknown project_id returns 404."""
    resp = await client.post(
        "/api/versions",
        json={
            "project_id": "nonexistent",
            "version_name": "v1.0",
            "artifact_ids": ["fake-aid"],
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_version_unknown_artifact_returns_422(client, mem_db):
    """POST /api/versions with an artifact_id not in the project returns 422."""
    pid = await seed_project(mem_db)

    resp = await client.post(
        "/api/versions",
        json={
            "project_id": pid,
            "version_name": "v1.0",
            "artifact_ids": ["not-a-real-artifact-id"],
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_version_returns_artifacts_with_is_active(client, mem_db):
    """GET /api/versions/{id} returns artifacts each with an is_active boolean."""
    pid = await seed_project(mem_db)
    aid1 = await seed_artifact(mem_db, pid, "Active Doc", is_active=True)
    aid2 = await seed_artifact(mem_db, pid, "Inactive Doc", is_active=False)
    vid = await seed_version(mem_db, pid, [aid1, aid2])

    resp = await client.get(f"/api/versions/{vid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["version_id"] == vid
    assert len(body["artifacts"]) == 2
    for art in body["artifacts"]:
        assert isinstance(art["is_active"], bool)
        assert "artifact_id" in art
        assert "title" in art


@pytest.mark.asyncio
async def test_get_version_unknown_returns_404(client, mem_db):
    """GET /api/versions/{unknown} returns 404."""
    resp = await client.get("/api/versions/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_versions_for_project(client, mem_db):
    """GET /api/projects/{id}/versions returns all versions with counts."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid], name="v1.0")

    resp = await client.get(f"/api/projects/{pid}/versions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert len(body["versions"]) == 1
    v = body["versions"][0]
    assert v["version_id"] == vid
    assert v["name"] == "v1.0"
    assert isinstance(v["artifact_count"], int)
    assert isinstance(v["review_count"], int)


@pytest.mark.asyncio
async def test_list_versions_unknown_project_returns_404(client, mem_db):
    """GET /api/projects/{unknown}/versions returns 404."""
    resp = await client.get("/api/projects/nonexistent/versions")
    assert resp.status_code == 404
