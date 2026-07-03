"""Milestone 5.6 — tests/api/test_proposals.py

Tests:
  - POST /api/proposals returns { proposal_id, status: "queued", error: null }
  - POST /api/proposals with unknown review_id returns 404 with error field
  - GET /api/proposals/{id}/status returns valid status value
  - GET /api/proposals/{unknown}/status returns 404
"""

from __future__ import annotations

import pytest

from .conftest import seed_artifact, seed_project, seed_review, seed_version

_VALID_STATUSES = {"queued", "running", "complete", "failed"}


@pytest.mark.asyncio
async def test_create_proposal_returns_queued(client, mem_db):
    """POST /api/proposals returns proposal_id, status='queued', error=null."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid])
    rid = await seed_review(mem_db, vid)

    resp = await client.post("/api/proposals", json={"review_id": rid})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["error"] is None
    assert "proposal_id" in body


@pytest.mark.asyncio
async def test_create_proposal_unknown_review_returns_404(client, mem_db):
    """POST /api/proposals with unknown review_id returns 404."""
    resp = await client.post("/api/proposals", json={"review_id": "nonexistent"})
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body or "error" in body


@pytest.mark.asyncio
async def test_get_proposal_status_valid(client, mem_db):
    """GET /api/proposals/{id}/status returns a recognised status value."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid])
    rid = await seed_review(mem_db, vid)

    create_resp = await client.post("/api/proposals", json={"review_id": rid})
    proposal_id = create_resp.json()["proposal_id"]

    resp = await client.get(f"/api/proposals/{proposal_id}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["proposal_id"] == proposal_id
    assert body["status"] in _VALID_STATUSES
    assert body["error"] is None


@pytest.mark.asyncio
async def test_get_proposal_status_unknown_returns_404(client, mem_db):
    """GET /api/proposals/{unknown}/status returns 404."""
    resp = await client.get("/api/proposals/nonexistent-proposal/status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_multiple_proposals_for_same_review(client, mem_db):
    """Two proposals can be created for the same review independently."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)
    vid = await seed_version(mem_db, pid, [aid])
    rid = await seed_review(mem_db, vid)

    r1 = await client.post("/api/proposals", json={"review_id": rid})
    r2 = await client.post("/api/proposals", json={"review_id": rid})

    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["proposal_id"] != r2.json()["proposal_id"]
