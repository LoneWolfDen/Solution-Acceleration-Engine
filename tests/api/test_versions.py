"""tests/api/test_versions.py — Version create, list, detail."""

import json
import pytest


def _artifact(client, project_id):
    return client.post(
        "/api/artifacts",
        data={"project_id": project_id, "title": "Artifact", "source": "paste", "content": "doc", "tags": "[]"},
    ).json()["artifact_id"]


def test_create_version_success(test_app, project_id):
    aid = _artifact(test_app, project_id)
    resp = test_app.post("/api/versions", json={"project_id": project_id, "version_name": "v1", "artifact_ids": [aid]})
    assert resp.status_code == 201
    data = resp.json()
    assert "version_id" in data
    assert data["artifact_count"] == 1
    assert data.get("error") is None


def test_create_version_empty_artifact_ids_returns_422(test_app, project_id):
    resp = test_app.post("/api/versions", json={"project_id": project_id, "version_name": "bad", "artifact_ids": []})
    assert resp.status_code == 422
    assert resp.json()["error"] is not None


def test_get_version_detail_has_artifacts(test_app, project_id):
    aid = _artifact(test_app, project_id)
    ver_id = test_app.post(
        "/api/versions", json={"project_id": project_id, "version_name": "v2", "artifact_ids": [aid]}
    ).json()["version_id"]
    resp = test_app.get(f"/api/versions/{ver_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "artifacts" in data
    assert len(data["artifacts"]) == 1
    assert isinstance(data["artifacts"][0]["is_active"], bool)


def test_list_versions_for_project(test_app, project_id):
    aid = _artifact(test_app, project_id)
    test_app.post("/api/versions", json={"project_id": project_id, "version_name": "v3", "artifact_ids": [aid]})
    resp = test_app.get(f"/api/projects/{project_id}/versions")
    assert resp.status_code == 200
    data = resp.json()
    assert "versions" in data
    assert len(data["versions"]) >= 1
    assert "version_id" in data["versions"][0]
    assert "artifact_count" in data["versions"][0]
