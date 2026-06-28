"""
tests/api/test_error_contract.py — Verify the standardised error envelope.

Every 4xx and 5xx response must carry a non-null ``error`` string.
Every 2xx success response must carry ``error: null``.
"""

import pytest


# ── 4xx errors carry a non-null error field ────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/api/projects/nonexistent",
    "/api/nodes/nonexistent",
    "/api/projects/nonexistent/versions",
    "/api/versions/nonexistent",
    "/api/versions/nonexistent/reviews",
])
def test_404_carries_error_field(test_app, path):
    resp = test_app.get(path)
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert data["error"] is not None


def test_422_on_bad_artifact_source(test_app, project_id):
    resp = test_app.post(
        "/api/artifacts",
        data={
            "project_id": project_id,
            "title": "Bad",
            "source": "invalid_source",
            "tags": "[]",
        },
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert data["error"] is not None


def test_422_on_empty_artifact_ids(test_app, project_id):
    resp = test_app.post(
        "/api/versions",
        json={
            "project_id": project_id,
            "version_name": "v",
            "artifact_ids": [],
        },
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert data["error"] is not None


def test_delete_unknown_artifact_returns_404(test_app):
    """DELETE /api/artifacts/{id} with a non-existent ID returns 404 with error."""
    resp = test_app.delete("/api/artifacts/does-not-exist")
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert data["error"] is not None


# ── 2xx responses carry error: null ───────────────────────────────────────────

def test_health_carries_error_null(test_app):
    data = test_app.get("/api/health").json()
    assert data.get("error") is None


def test_projects_list_carries_error_null(test_app):
    data = test_app.get("/api/projects").json()
    assert data.get("error") is None


def test_admin_health_carries_error_null(test_app):
    data = test_app.get("/api/admin/health").json()
    assert data.get("error") is None


def test_admin_config_carries_error_null(test_app):
    data = test_app.get("/api/admin/config").json()
    assert data.get("error") is None
