"""tests/api/test_artifacts.py — Artifact CRUD and tag suggestions."""

import json
import pytest


def _create(client, project_id, title="Test Doc", source="paste", content="scope and risk doc", tags=None):
    return client.post(
        "/api/artifacts",
        data={
            "project_id": project_id,
            "title": title,
            "source": source,
            "content": content,
            "tags": json.dumps(tags or []),
        },
    )


def test_list_artifacts_includes_is_active(test_app, project_id):
    resp = test_app.get(f"/api/projects/{project_id}/artifacts")
    assert resp.status_code == 200
    for a in resp.json()["artifacts"]:
        assert "is_active" in a
        assert isinstance(a["is_active"], bool)


def test_create_artifact_paste(test_app, project_id):
    resp = _create(test_app, project_id)
    assert resp.status_code == 201
    data = resp.json()
    assert "artifact_id" in data
    assert data["is_active"] is True
    assert data.get("error") is None


def test_create_artifact_with_tags(test_app, project_id):
    resp = _create(test_app, project_id, tags=["risk", "scope"])
    assert set(resp.json()["tags"]) == {"risk", "scope"}


def test_create_artifact_url(test_app, project_id):
    resp = test_app.post(
        "/api/artifacts",
        data={"project_id": project_id, "title": "URL", "source": "url",
              "url": "https://example.com/doc.pdf", "tags": "[]"},
    )
    assert resp.status_code == 201
    assert resp.json().get("error") is None


def test_patch_artifact_sets_inactive(test_app, project_id):
    aid = _create(test_app, project_id).json()["artifact_id"]
    resp = test_app.patch(f"/api/artifacts/{aid}", json={"active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_patch_unknown_artifact_returns_404(test_app):
    resp = test_app.patch("/api/artifacts/does-not-exist", json={"active": False})
    assert resp.status_code == 404
    assert resp.json()["error"] is not None


def test_delete_artifact(test_app, project_id):
    aid = _create(test_app, project_id, title="To Delete").json()["artifact_id"]
    resp = test_app.delete(f"/api/artifacts/{aid}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


def test_suggestions_returns_list_no_llm(test_app):
    resp = test_app.get(
        "/api/artifacts/suggestions",
        params={"filename": "banking_sow.md", "content_preview": "statement of work covering scope and risk"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["suggestions"], list)
    assert data.get("error") is None


def test_suggestions_contains_sow_tag(test_app):
    resp = test_app.get("/api/artifacts/suggestions", params={"filename": "sow.md", "content_preview": "statement of work"})
    assert "sow" in resp.json()["suggestions"]
