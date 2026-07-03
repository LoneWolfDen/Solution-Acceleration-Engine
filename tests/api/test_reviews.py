"""Milestone 5.5 — tests/api/test_reviews.py

Tests:
  - POST /api/reviews returns { review_id, status: "queued", error: null }
  - GET /api/reviews/{id}/status returns valid status enum value
  - GET /api/nodes/{node_id} returns NodeDetailResponse with findings array
  - GET /api/nodes/{unknown_id} returns 404 with error field
  - GET /api/versions/{id}/reviews returns list of reviews
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from .conftest import (
    seed_artifact,
    seed_project,
    seed_review,
    seed_version,
)

_VALID_STATUSES = {"queued", "running", "complete", "failed"}


@pytest.mark.asyncio
async def test_create_review_returns_queued(client, mem_db):
    """POST /api/reviews returns review_id, status='queued', error=null."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid])

    resp = await client.post(
        "/api/reviews",
        json={"version_id": vid, "persona_roles": ["architect"], "context": ""},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["error"] is None
    assert "review_id" in body


@pytest.mark.asyncio
async def test_create_review_unknown_version_returns_404(client, mem_db):
    """POST /api/reviews with unknown version_id returns 404."""
    resp = await client.post(
        "/api/reviews",
        json={"version_id": "nonexistent", "persona_roles": [], "context": ""},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_review_status_valid_enum(client, mem_db):
    """GET /api/reviews/{id}/status returns a recognised status value."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid])
    rid = await seed_review(mem_db, vid, status="queued")

    resp = await client.get(f"/api/reviews/{rid}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_id"] == rid
    assert body["status"] in _VALID_STATUSES
    assert body["error"] is None


@pytest.mark.asyncio
async def test_get_review_status_complete(client, mem_db):
    """Status endpoint returns 'complete' for a completed review."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid])
    rid = await seed_review(mem_db, vid, status="complete")

    resp = await client.get(f"/api/reviews/{rid}/status")
    assert resp.json()["status"] == "complete"


@pytest.mark.asyncio
async def test_get_review_status_unknown_returns_404(client, mem_db):
    """GET /api/reviews/{unknown}/status returns 404."""
    resp = await client.get("/api/reviews/nonexistent/status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_reviews_for_version(client, mem_db):
    """GET /api/versions/{id}/reviews returns all reviews with required fields."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid])
    rid = await seed_review(mem_db, vid)

    resp = await client.get(f"/api/versions/{vid}/reviews")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert len(body["reviews"]) == 1
    r = body["reviews"][0]
    assert r["review_id"] == rid
    assert "run_date" in r
    assert "status" in r
    assert "persona" in r


@pytest.mark.asyncio
async def test_list_reviews_unknown_version_returns_404(client, mem_db):
    """GET /api/versions/{unknown}/reviews returns 404."""
    resp = await client.get("/api/versions/nonexistent/reviews")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_node_with_findings(client, mem_db):
    """GET /api/nodes/{id} returns NodeDetailResponse with findings array."""
    # Seed a node with content_markdown containing a ReviewNodePayload-style JSON.
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid])
    rid = await seed_review(mem_db, vid)

    # Create a node record with synthetic content.
    node_id = str(uuid.uuid4())
    payload = {
        "dimension": "Risk",
        "findings": [
            {
                "dimension": "Risk",
                "confidence": "RED",
                "summary": "Delivery risk identified",
                "detail": "The project timeline is aggressive.",
                "citations": [
                    {
                        "file_path": "scope.md",
                        "line_start": 1,
                        "line_end": 5,
                        "citation_type": "Direct Reference",
                        "excerpt": "Timeline: 6 months",
                    }
                ],
                "mitigation_routing": "Risk Register",
            }
        ],
        "overall_confidence": "RED",
        "raw_llm_response": "{}",
    }
    now = datetime.now(timezone.utc).isoformat()
    await mem_db.execute(
        "INSERT INTO nodes (id, project_id, version_id, parent_id, layer_type, node_name, "
        "metadata_json, content_markdown, created_at) VALUES (?, ?, ?, NULL, 'exploration', "
        "'Test Node', '{}', ?, ?)",
        (node_id, pid, vid, json.dumps(payload), now),
    )
    # Link review to node.
    await mem_db.execute(
        "UPDATE reviews SET node_id = ? WHERE id = ?", (node_id, rid)
    )
    await mem_db.commit()

    resp = await client.get(f"/api/nodes/{node_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert isinstance(body["findings"], list)
    assert len(body["findings"]) == 1
    assert "summary" in body
    assert body["project_id"] == pid


@pytest.mark.asyncio
async def test_get_node_unknown_returns_404(client, mem_db):
    """GET /api/nodes/{unknown_id} returns 404 with error field."""
    resp = await client.get("/api/nodes/nonexistent-node-id")
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body or "error" in body
