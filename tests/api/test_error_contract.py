"""tests/api/test_error_contract.py — Error envelope contract."""

import pytest


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


def test_patch_unknown_artifact_returns_404(test_app):
    resp = test_app.patch("/api/artifacts/does-not-exist", json={"active": False})
    assert resp.status_code == 404
    assert resp.json()["error"] is not None


def test_422_on_bad_artifact_source(test_app, project_id):
    resp = test_app.post("/api/artifacts", data={"project_id": project_id, "title": "Bad", "source": "invalid_source", "tags": "[]"})
    assert resp.status_code == 422
    assert resp.json()["error"] is not None


def test_422_on_empty_artifact_ids(test_app, project_id):
    resp = test_app.post("/api/versions", json={"project_id": project_id, "version_name": "v", "artifact_ids": []})
    assert resp.status_code == 422
    assert resp.json()["error"] is not None


def test_health_carries_error_null(test_app):
    assert test_app.get("/api/health").json().get("error") is None


def test_projects_list_carries_error_null(test_app):
    assert test_app.get("/api/projects").json().get("error") is None


def test_admin_health_carries_error_null(test_app):
    assert test_app.get("/api/admin/health").json().get("error") is None


def test_admin_config_carries_error_null(test_app):
    assert test_app.get("/api/admin/config").json().get("error") is None
