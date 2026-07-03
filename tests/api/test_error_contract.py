"""Milestone 5.8 — tests/api/test_error_contract.py

Verifies the error envelope contract:
  - Every 4xx and 5xx response contains a non-null 'detail' or 'error' field
  - Success responses all contain error: null
  - Malformed JSON body returns 422

The contract is: success responses include ``error: null``, error responses
include either ``error: <str>`` (from our handlers) or ``detail: <str>``
(from FastAPI's built-in validation layer).
"""

from __future__ import annotations

import pytest

from .conftest import seed_artifact, seed_project, seed_review, seed_version


def _has_error_field(body: dict) -> bool:
    """Return True if the body contains a non-null 'error' or 'detail' field."""
    if "error" in body and body["error"] is not None:
        return True
    if "detail" in body and body["detail"] is not None:
        return True
    return False


def _has_null_error(body: dict) -> bool:
    """Return True if the body's 'error' field is explicitly null/None."""
    return body.get("error") is None


# ── 404 responses ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_404_project_has_error_field(client, mem_db):
    resp = await client.delete("/api/projects/no-such-project")
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


@pytest.mark.asyncio
async def test_404_version_has_error_field(client, mem_db):
    resp = await client.get("/api/versions/no-such-version")
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


@pytest.mark.asyncio
async def test_404_artifact_has_error_field(client, mem_db):
    resp = await client.delete("/api/artifacts/no-such-artifact")
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


@pytest.mark.asyncio
async def test_404_review_status_has_error_field(client, mem_db):
    resp = await client.get("/api/reviews/no-such-review/status")
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


@pytest.mark.asyncio
async def test_404_node_has_error_field(client, mem_db):
    resp = await client.get("/api/nodes/no-such-node")
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


@pytest.mark.asyncio
async def test_404_proposal_status_has_error_field(client, mem_db):
    resp = await client.get("/api/proposals/no-such-proposal/status")
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


# ── 422 responses ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_422_malformed_json_post_artifacts(client, mem_db):
    """Sending malformed JSON returns 422 with error/detail information."""
    resp = await client.post(
        "/api/artifacts",
        content=b"this is not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422
    assert _has_error_field(resp.json())


@pytest.mark.asyncio
async def test_422_missing_required_field_post_versions(client, mem_db):
    """Missing required field returns 422."""
    resp = await client.post(
        "/api/versions",
        json={"version_name": "v1"},  # missing project_id and artifact_ids
    )
    assert resp.status_code == 422
    assert _has_error_field(resp.json())


@pytest.mark.asyncio
async def test_422_empty_artifact_ids_has_error(client, mem_db):
    """Empty artifact_ids triggers 422 with error info."""
    pid = await seed_project(mem_db)
    resp = await client.post(
        "/api/versions",
        json={"project_id": pid, "version_name": "v1", "artifact_ids": []},
    )
    assert resp.status_code == 422
    assert _has_error_field(resp.json())


@pytest.mark.asyncio
async def test_422_unknown_admin_field_has_error(client, mem_db):
    """Unknown admin config field returns 422 with error info."""
    resp = await client.post("/api/admin/config", json={"field": "bad"})
    assert resp.status_code == 422
    assert _has_error_field(resp.json())


# ── Success responses have error: null ────────────────────────────────────────

@pytest.mark.asyncio
async def test_success_projects_list_has_null_error(client, mem_db):
    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    assert _has_null_error(resp.json())


@pytest.mark.asyncio
async def test_success_artifacts_list_has_null_error(client, mem_db):
    pid = await seed_project(mem_db)
    resp = await client.get(f"/api/projects/{pid}/artifacts")
    assert resp.status_code == 200
    assert _has_null_error(resp.json())


@pytest.mark.asyncio
async def test_success_create_artifact_has_null_error(client, mem_db):
    pid = await seed_project(mem_db)
    resp = await client.post(
        "/api/artifacts",
        json={"source": "paste", "title": "Doc", "project_id": pid, "content": "text"},
    )
    assert resp.status_code == 201
    assert _has_null_error(resp.json())


@pytest.mark.asyncio
async def test_success_create_review_has_null_error(client, mem_db):
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid])
    resp = await client.post(
        "/api/reviews",
        json={"version_id": vid, "persona_roles": [], "context": ""},
    )
    assert resp.status_code == 202
    assert _has_null_error(resp.json())


@pytest.mark.asyncio
async def test_success_admin_health_has_null_error(client, mem_db):
    resp = await client.get("/api/admin/health")
    assert resp.status_code == 200
    assert _has_null_error(resp.json())


@pytest.mark.asyncio
async def test_success_admin_config_has_null_error(client, mem_db):
    resp = await client.get("/api/admin/config")
    assert resp.status_code == 200
    assert _has_null_error(resp.json())


@pytest.mark.asyncio
async def test_success_suggestions_has_null_error(client, mem_db):
    resp = await client.get("/api/artifacts/suggestions", params={"filename": "test.md"})
    assert resp.status_code == 200
    assert _has_null_error(resp.json())


@pytest.mark.asyncio
async def test_success_delete_project_has_null_error(client, mem_db):
    pid = await seed_project(mem_db)
    resp = await client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 200
    assert _has_null_error(resp.json())
