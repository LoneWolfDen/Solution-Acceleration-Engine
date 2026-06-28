"""
tests/api/test_reviews.py — Review job lifecycle tests.
"""

import json
import pytest


def _setup_version(client, project_id):
    """Create an artifact and a version, return version_id."""
    aid = client.post(
        "/api/artifacts",
        data={
            "project_id": project_id,
            "title": "Review Artifact",
            "source": "paste",
            "content": "content for review",
            "tags": "[]",
        },
    ).json()["artifact_id"]

    return client.post(
        "/api/versions",
        json={"project_id": project_id, "version_name": "v1", "artifact_ids": [aid]},
    ).json()["version_id"]


def test_create_review_returns_queued(test_app, project_id):
    ver_id = _setup_version(test_app, project_id)
    resp = test_app.post(
        "/api/reviews",
        json={"version_id": ver_id, "persona_roles": ["Architect"], "context": ""},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "review_id" in data
    assert data["status"] == "queued"
    assert data.get("error") is None


def test_get_review_status_valid_enum(test_app, project_id):
    ver_id = _setup_version(test_app, project_id)
    review_id = test_app.post(
        "/api/reviews",
        json={"version_id": ver_id, "persona_roles": ["PM"], "context": ""},
    ).json()["review_id"]

    resp = test_app.get(f"/api/reviews/{review_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in {"queued", "running", "complete", "failed"}
    assert data.get("error") is None


def test_get_review_payload_from_node(test_app, project_id):
    ver_id = _setup_version(test_app, project_id)
    review_id = test_app.post(
        "/api/reviews",
        json={"version_id": ver_id, "persona_roles": ["PM"], "context": ""},
    ).json()["review_id"]

    resp = test_app.get(f"/api/nodes/{review_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "review_id" in data
    assert "findings" in data
    assert isinstance(data["findings"], list)
    assert data.get("error") is None


def test_get_node_unknown_returns_404(test_app):
    resp = test_app.get("/api/nodes/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"] is not None


def test_list_reviews_for_version(test_app, project_id):
    ver_id = _setup_version(test_app, project_id)
    test_app.post(
        "/api/reviews",
        json={"version_id": ver_id, "persona_roles": ["Architect"], "context": ""},
    )
    resp = test_app.get(f"/api/versions/{ver_id}/reviews")
    assert resp.status_code == 200
    data = resp.json()
    assert "reviews" in data
    r = data["reviews"][0]
    assert "review_id" in r
    assert "status" in r
    assert "persona" in r
