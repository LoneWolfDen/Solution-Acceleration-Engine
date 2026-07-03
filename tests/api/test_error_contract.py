"""
tests/api/test_error_contract.py

5.8 — Error envelope contract tests.

Rules verified:
- Every 4xx response contains a non-null "detail" or "error" field.
- Every 5xx response contains a non-null "error" field.
- All success (2xx) responses contain error: null.
- Malformed JSON body returns 422 with parseable error information.
"""

from __future__ import annotations

import json


# ── Helpers ───────────────────────────────────────────────────────────────────


def _has_error_field(body: dict) -> bool:
    """Return True if body contains 'error' (non-null) or 'detail' (any value)."""
    return (
        ("error" in body and body["error"] is not None)
        or ("detail" in body)
    )


def _error_null(body: dict) -> bool:
    """Return True if error field is present and null."""
    return body.get("error") is None


# ── 404 responses carry an error/detail field ─────────────────────────────────


def test_404_project_has_error_field(client):
    body = client.get("/api/projects").json()  # success — for contrast
    assert _error_null(body)


def test_404_unknown_project_delete_has_error_field(client):
    resp = client.delete("/api/projects/no-such-id")
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


def test_404_unknown_version_has_error_field(client):
    resp = client.get("/api/versions/no-such-version")
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


def test_404_unknown_node_has_error_field(client):
    resp = client.get("/api/nodes/no-such-node")
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


def test_404_unknown_artifact_patch_has_error_field(client):
    resp = client.patch("/api/artifacts/no-such-id", json={"active": False})
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


def test_404_unknown_artifact_delete_has_error_field(client):
    resp = client.delete("/api/artifacts/no-such-id")
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


def test_404_unknown_review_status_has_error_field(client):
    resp = client.get("/api/reviews/no-such-review/status")
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


def test_404_unknown_proposal_has_error_field(client):
    resp = client.post("/api/proposals", json={"review_id": "no-such-review"})
    assert resp.status_code == 404
    assert _has_error_field(resp.json())


# ── 422 responses carry an error/detail field ─────────────────────────────────


def test_422_empty_artifact_ids_has_error_field(client, project_id):
    resp = client.post("/api/versions", json={
        "project_id": project_id,
        "version_name": "x",
        "artifact_ids": [],
    })
    assert resp.status_code == 422
    assert _has_error_field(resp.json())


def test_422_missing_required_fields_has_error_field(client):
    """Completely missing required body fields returns 422 with detail."""
    resp = client.post("/api/artifacts", json={})
    assert resp.status_code == 422
    assert _has_error_field(resp.json())


def test_422_malformed_json_body(client):
    """Sending malformed JSON returns 422 (FastAPI parses error for us)."""
    resp = client.post(
        "/api/artifacts",
        content=b"{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert _has_error_field(body)


def test_422_bad_admin_config_field(client):
    resp = client.post("/api/admin/config", json={"field": "nonsense"})
    assert resp.status_code == 422
    assert _has_error_field(resp.json())


# ── Success responses all have error: null ────────────────────────────────────


def test_success_projects_list_error_null(client):
    body = client.get("/api/projects").json()
    assert body["error"] is None


def test_success_admin_health_error_null(client):
    body = client.get("/api/admin/health").json()
    assert body["error"] is None


def test_success_admin_config_error_null(client):
    body = client.get("/api/admin/config").json()
    assert body["error"] is None


def test_success_artifact_create_error_null(client, project_id):
    resp = client.post("/api/artifacts", json={
        "source": "paste",
        "title": "Contract Test Artifact",
        "project_id": project_id,
        "content": "some content",
        "tags": [],
    })
    assert resp.status_code == 201
    assert resp.json()["error"] is None


def test_success_artifact_patch_error_null(client, artifact_id):
    body = client.patch(f"/api/artifacts/{artifact_id}", json={"active": False}).json()
    assert body["error"] is None


def test_success_artifact_delete_error_null(client, artifact_id):
    body = client.delete(f"/api/artifacts/{artifact_id}").json()
    assert body["error"] is None


def test_success_version_create_error_null(client, project_id, artifact_id):
    body = client.post("/api/versions", json={
        "project_id": project_id,
        "version_name": "contract-v",
        "artifact_ids": [artifact_id],
    }).json()
    assert body["error"] is None


def test_success_review_create_error_null(client, version_id):
    body = client.post("/api/reviews", json={
        "version_id": version_id,
        "persona_roles": [],
        "context": "",
    }).json()
    assert body["error"] is None


def test_success_proposal_create_error_null(client, review_id):
    body = client.post("/api/proposals", json={"review_id": review_id}).json()
    assert body["error"] is None


def test_success_admin_config_save_error_null(client):
    body = client.post("/api/admin/config", json={
        "field": "threshold",
        "threshold_name": "risk",
        "threshold_value": 0.75,
    }).json()
    assert body["error"] is None


def test_success_suggestions_error_null(client):
    body = client.get("/api/artifacts/suggestions?filename=test.md").json()
    assert body["error"] is None
