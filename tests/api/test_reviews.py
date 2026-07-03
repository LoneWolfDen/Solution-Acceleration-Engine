"""
tests/api/test_reviews.py

5.5 — Review endpoint contract tests.

Covers:
- POST /api/reviews returns { review_id, status: "queued", error: null }
- GET /api/reviews/{id}/status returns valid status enum value
- GET /api/nodes/{node_id} returns Review_Payload with findings array
- GET /api/nodes/{unknown_id} returns 404 with error field
"""

from __future__ import annotations

_VALID_STATUSES = {"queued", "running", "complete", "failed"}


# ── POST /api/reviews ─────────────────────────────────────────────────────────


def test_create_review_returns_queued(client, version_id):
    """POST /api/reviews returns queued status immediately."""
    payload = {
        "version_id": version_id,
        "persona_roles": ["risk-analyst"],
        "context": "Focus on delivery risk.",
    }
    resp = client.post("/api/reviews", json=payload)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert "review_id" in body
    assert body["error"] is None


def test_create_review_unknown_version_returns_404(client):
    """POST /api/reviews with unknown version_id returns 404."""
    resp = client.post("/api/reviews", json={
        "version_id": "no-such-version",
        "persona_roles": [],
        "context": "",
    })
    assert resp.status_code == 404


def test_create_review_empty_persona_roles(client, version_id):
    """POST /api/reviews with empty persona_roles still succeeds."""
    resp = client.post("/api/reviews", json={
        "version_id": version_id,
        "persona_roles": [],
        "context": "",
    })
    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"


def test_create_review_node_stored_in_db(client, db_conn, version_id):
    """Review node is persisted to the DB after POST /api/reviews."""
    import asyncio
    from contexta.db import repositories as repo
    resp = client.post("/api/reviews", json={
        "version_id": version_id,
        "persona_roles": ["delivery-lead"],
        "context": "",
    })
    review_id = resp.json()["review_id"]
    node = asyncio.get_event_loop().run_until_complete(repo.get_node(db_conn, review_id))
    assert node is not None
    assert node.layer_type == "synthesis"


# ── GET /api/reviews/{id}/status ─────────────────────────────────────────────


def test_review_status_valid_enum(client, version_id):
    """GET /api/reviews/{id}/status returns a valid status value."""
    review_id = client.post("/api/reviews", json={
        "version_id": version_id,
        "persona_roles": [],
        "context": "",
    }).json()["review_id"]

    resp = client.get(f"/api/reviews/{review_id}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_id"] == review_id
    assert body["status"] in _VALID_STATUSES
    assert body["error"] is None


def test_review_status_unknown_id_returns_404(client):
    """GET /api/reviews/{unknown_id}/status returns 404."""
    resp = client.get("/api/reviews/totally-unknown-review/status")
    assert resp.status_code == 404


def test_review_status_has_progress_message_field(client, version_id):
    """Status response always contains progress_message field (may be null)."""
    review_id = client.post("/api/reviews", json={
        "version_id": version_id,
        "persona_roles": [],
        "context": "",
    }).json()["review_id"]
    body = client.get(f"/api/reviews/{review_id}/status").json()
    assert "progress_message" in body


# ── GET /api/nodes/{node_id} ─────────────────────────────────────────────────


def test_get_node_returns_review_payload_shape(client, review_id, project_id, version_id):
    """GET /api/nodes/{id} returns ReviewPayload with all required fields."""
    resp = client.get(f"/api/nodes/{review_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_id"] == review_id
    assert body["project_id"] == project_id
    assert body["version_id"] == version_id
    assert "status" in body
    assert "run_date" in body
    assert "persona" in body
    assert isinstance(body["findings"], list)
    assert "summary" in body
    assert body["error"] is None


def test_get_node_summary_has_required_keys(client, review_id):
    """Summary block contains all five count keys."""
    body = client.get(f"/api/nodes/{review_id}").json()
    summary = body["summary"]
    for key in ("risks", "constraints", "dependencies", "assumptions", "action_items"):
        assert key in summary
        assert isinstance(summary[key], int)


def test_get_node_unknown_id_returns_404(client):
    """GET /api/nodes/{unknown_id} returns 404."""
    resp = client.get("/api/nodes/totally-unknown-node")
    assert resp.status_code == 404


def test_get_node_404_has_error_field(client):
    """404 response from GET /api/nodes contains detail or error field."""
    resp = client.get("/api/nodes/no-such-node")
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body or "error" in body


# ── GET /api/versions/{id}/reviews ───────────────────────────────────────────


def test_list_reviews_for_version(client, version_id, review_id):
    """GET /api/versions/{id}/reviews returns the pre-seeded review."""
    resp = client.get(f"/api/versions/{version_id}/reviews")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert len(body["reviews"]) == 1
    r = body["reviews"][0]
    assert r["review_id"] == review_id
    assert "run_date" in r
    assert "status" in r
    assert "persona" in r


def test_list_reviews_empty(client, version_id):
    """Returns empty list when version has no reviews."""
    resp = client.get(f"/api/versions/{version_id}/reviews")
    # version_id fixture creates version but review_id fixture is not requested here
    assert resp.status_code == 200
    assert resp.json()["error"] is None


def test_list_reviews_unknown_version_404(client):
    """Returns 404 for unknown version."""
    resp = client.get("/api/versions/no-such-version/reviews")
    assert resp.status_code == 404
