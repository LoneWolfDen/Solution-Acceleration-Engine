"""
tests/api/test_proposals.py

5.6 — Proposal endpoint contract tests.

Covers:
- POST /api/proposals returns { proposal_id, status: "queued", error: null }
- POST /api/proposals with unknown review_id returns 404 with error field
- GET /api/proposals/{id}/status returns valid status
"""

from __future__ import annotations

_VALID_STATUSES = {"queued", "running", "complete", "failed"}


# ── POST /api/proposals ───────────────────────────────────────────────────────


def test_create_proposal_returns_queued(client, review_id):
    """POST /api/proposals returns queued status immediately."""
    resp = client.post("/api/proposals", json={"review_id": review_id})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert "proposal_id" in body
    assert body["error"] is None


def test_create_proposal_unknown_review_returns_404(client):
    """POST /api/proposals with unknown review_id returns 404."""
    resp = client.post("/api/proposals", json={"review_id": "no-such-review"})
    assert resp.status_code == 404


def test_create_proposal_node_stored_in_db(client, db_conn, review_id):
    """Proposal node is persisted to DB after POST."""
    import asyncio
    from contexta.db import repositories as repo
    proposal_id = client.post(
        "/api/proposals", json={"review_id": review_id}
    ).json()["proposal_id"]
    node = asyncio.get_event_loop().run_until_complete(repo.get_node(db_conn, proposal_id))
    assert node is not None
    assert node.parent_id == review_id


def test_create_multiple_proposals_for_same_review(client, review_id):
    """Can create multiple proposals for the same review_id."""
    id1 = client.post("/api/proposals", json={"review_id": review_id}).json()["proposal_id"]
    id2 = client.post("/api/proposals", json={"review_id": review_id}).json()["proposal_id"]
    assert id1 != id2


# ── GET /api/proposals/{id}/status ───────────────────────────────────────────


def test_proposal_status_valid_enum(client, review_id):
    """GET /api/proposals/{id}/status returns a valid status value."""
    proposal_id = client.post(
        "/api/proposals", json={"review_id": review_id}
    ).json()["proposal_id"]

    resp = client.get(f"/api/proposals/{proposal_id}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["proposal_id"] == proposal_id
    assert body["status"] in _VALID_STATUSES
    assert body["error"] is None


def test_proposal_status_unknown_id_returns_404(client):
    """GET /api/proposals/{unknown_id}/status returns 404."""
    resp = client.get("/api/proposals/totally-unknown-proposal/status")
    assert resp.status_code == 404


def test_proposal_status_has_progress_message_field(client, review_id):
    """Status response always has progress_message field (may be null)."""
    proposal_id = client.post(
        "/api/proposals", json={"review_id": review_id}
    ).json()["proposal_id"]
    body = client.get(f"/api/proposals/{proposal_id}/status").json()
    assert "progress_message" in body
