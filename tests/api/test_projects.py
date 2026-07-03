"""tests/api/test_projects.py — Project list and delete."""

import pytest


def test_list_projects_returns_list(test_app):
    resp = test_app.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert "projects" in data
    assert data.get("error") is None


def test_list_projects_required_fields(test_app, project_id):
    projects = test_app.get("/api/projects").json()["projects"]
    assert len(projects) >= 1
    p = projects[0]
    for field in ("project_id", "name", "version_count", "review_count", "storage_bytes"):
        assert field in p


def test_delete_project_response_shape(test_app, project_id):
    resp = test_app.delete(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    assert data.get("error") is None


def test_delete_unknown_project_returns_404(test_app):
    resp = test_app.delete("/api/projects/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"] is not None


def test_get_project_detail(test_app, project_id):
    resp = test_app.get(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data or "project_id" in data
    assert "versions" in data
    assert "nodes" in data
    assert data.get("error") is None
