"""
tests/api/test_versions.py — Version create, list, and detail.
"""

import json
import pytest


def _create_artifact(client, project_id):
    return client.post(
        "/api/artifacts",
        data={
            "project_id": project_id,
            "title": "Artifact for Version",
            "source": "paste",
            "content": "doc content",
            "tags": "[]",
        },
    ).json()["artifact_id"]


def test_create_version_success(test_app, project_id):
    aid = _create_artifact(test_app, project_id)
    resp = test_app.post(
        "/api/versions",
        json={
            "project_id": project_id,
            "version_name": "v1.0",
            "artifact_ids": [aid],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "version_id" in data
    assert data["name"] == "v1.0"
    assert data["artifact_count"] == 1
    assert data.get("error") is None


def test_create_version_empty_artifact_ids_returns_422(test_app, project_id):
    resp = test_app.post(
        "/api/versions",
        json={
            "project_id": project_id,
            "version_name": "bad",
            "artifact_ids": [],
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"] is not None


def test_get_version_detail_has_artifacts(test_app, project_id):
    aid = _create_artifact(test_app, project_id)
    ver_id = test_app.post(
        "/api/versions",
        json={"project_id": project_id, "version_name": "v2", "artifact_ids": [aid]},
    ).json()["version_id"]

    resp = test_app.get(f"/api/versions/{ver_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "artifacts" in data
    assert len(data["artifacts"]) == 1
    art = data["artifacts"][0]
    assert "is_active" in art
    assert isinstance(art["is_active"], bool)


def test_list_versions_for_project(test_app, project_id):
    aid = _create_artifact(test_app, project_id)
    test_app.post(
        "/api/versions",
        json={"project_id": project_id, "version_name": "v3", "artifact_ids": [aid]},
    )
    resp = test_app.get(f"/api/projects/{project_id}/versions")
    assert resp.status_code == 200
    data = resp.json()
    assert "versions" in data
    assert len(data["versions"]) >= 1
    v = data["versions"][0]
    assert "version_id" in v
    assert "artifact_count" in v
