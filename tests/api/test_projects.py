"""
tests/api/test_projects.py — GET /api/projects and DELETE /api/projects/{id}.
"""

import pytest


def test_list_projects_returns_list(test_app):
    resp = test_app.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert "projects" in data
    assert data.get("error") is None


def test_list_projects_required_fields(test_app, project_id):
    resp = test_app.get("/api/projects")
    projects = resp.json()["projects"]
    assert len(projects) >= 1
    p = projects[0]
    assert "project_id" in p
    assert "name" in p
    assert "version_count" in p
    assert "review_count" in p
    assert "storage_bytes" in p


def test_list_projects_empty_when_none(test_app):
    """DELETE the only project then check the list is empty."""
    resp = test_app.delete("/api/projects/proj-1")
    assert resp.status_code == 200
    resp2 = test_app.get("/api/projects")
    assert resp2.json()["projects"] == []


def test_delete_project_response_shape(test_app, project_id):
    resp = test_app.delete(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    assert data.get("error") is None


def test_delete_unknown_project_returns_404(test_app):
    resp = test_app.delete("/api/projects/does-not-exist")
    assert resp.status_code == 404
    assert "error" in resp.json()
    assert resp.json()["error"] is not None
