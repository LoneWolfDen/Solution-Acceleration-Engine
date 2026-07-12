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


# ── Requirement A1: Project-scoped proposal aggregation (additive) ──────────


def _setup_version_with_complete_review(client, project_id, event_loop, version_name="v1"):
    """Create a version with one artifact, one review job, and force it to
    'complete' status directly via the review_jobs table so a proposal can be
    created against it (mirrors the pipeline's terminal state)."""
    from contexta.api import repositories as api_repo

    aid = client.post(
        "/api/artifacts",
        data={"project_id": project_id, "title": "Art", "source": "paste",
              "content": "content", "tags": "[]"},
    ).json()["artifact_id"]
    version_id = client.post(
        "/api/versions",
        json={"project_id": project_id, "version_name": version_name, "artifact_ids": [aid]},
    ).json()["version_id"]
    review_id = client.post(
        "/api/reviews",
        json={"version_id": version_id, "persona_roles": ["Architect"], "context": ""},
    ).json()["review_id"]

    # Force the review job to 'complete' so it is eligible to feed a proposal.
    conn = client.app.state.db
    event_loop.run_until_complete(
        api_repo.update_review_job_status(conn, review_id, status="complete")
    )
    return version_id, review_id


def test_project_scoped_proposals_aggregates_across_versions(test_app, project_id, event_loop):
    """2 versions, 1 proposal each — both appear via the project endpoint
    with correct version_id."""
    v1, r1 = _setup_version_with_complete_review(test_app, project_id, event_loop, "v1")
    v2, r2 = _setup_version_with_complete_review(test_app, project_id, event_loop, "v2")

    p1 = test_app.post(f"/api/versions/{v1}/proposals", json={"review_ids": [r1]})
    assert p1.status_code == 202
    p2 = test_app.post(f"/api/versions/{v2}/proposals", json={"review_ids": [r2]})
    assert p2.status_code == 202

    resp = test_app.get(f"/api/projects/{project_id}/proposals")
    assert resp.status_code == 200
    proposals = resp.json()["proposals"]
    assert len(proposals) == 2
    version_ids = {p["version_id"] for p in proposals}
    assert version_ids == {v1, v2}


def test_project_scoped_proposals_unknown_project_404(test_app):
    resp = test_app.get("/api/projects/no-such-project/proposals")
    assert resp.status_code == 404
    assert resp.json()["error"] is not None


def test_project_scoped_proposals_empty_when_no_proposals(test_app, project_id):
    resp = test_app.get(f"/api/projects/{project_id}/proposals")
    assert resp.status_code == 200
    assert resp.json()["proposals"] == []


def test_version_scoped_proposals_endpoint_unchanged_by_project_endpoint(
    test_app, project_id, event_loop
):
    """Regression guard: the existing version-scoped endpoint's guard and
    shape are untouched by the additive project-scoped endpoint."""
    v1, r1 = _setup_version_with_complete_review(test_app, project_id, event_loop, "v1")
    test_app.post(f"/api/versions/{v1}/proposals", json={"review_ids": [r1]})

    resp = test_app.get(f"/api/versions/{v1}/proposals")
    assert resp.status_code == 200
    proposals = resp.json()["proposals"]
    assert len(proposals) == 1
    assert proposals[0]["version_id"] == v1

    # 422 guard on invalid review_ids still applies unchanged.
    bad_resp = test_app.post(
        f"/api/versions/{v1}/proposals", json={"review_ids": ["no-such-review"]}
    )
    assert bad_resp.status_code == 422
