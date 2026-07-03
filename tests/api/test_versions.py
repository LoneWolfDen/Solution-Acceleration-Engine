"""
tests/api/test_versions.py

5.4 — Version endpoint contract tests.

Covers:
- POST /api/versions creates version with correct artifact_ids
- GET /api/versions/{id} returns artifacts with is_active field
- POST /api/versions with empty artifact_ids returns 422 with error field
- GET /api/projects/{id}/versions returns summary list
"""

from __future__ import annotations


# ── GET /api/projects/{id}/versions ──────────────────────────────────────────


def test_list_versions_empty(client, project_id):
    """Returns empty list when project has no versions."""
    resp = client.get(f"/api/projects/{project_id}/versions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["versions"] == []
    assert body["error"] is None


def test_list_versions_required_fields(client, project_id, version_id):
    """Each version summary contains all required fields."""
    resp = client.get(f"/api/projects/{project_id}/versions")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["versions"]) == 1
    v = body["versions"][0]
    assert v["version_id"] == version_id
    assert v["name"] == "v1.0"
    assert "created_at" in v
    assert isinstance(v["artifact_count"], int)
    assert isinstance(v["review_count"], int)
    assert body["error"] is None


def test_list_versions_unknown_project_404(client):
    """Returns 404 for unknown project."""
    resp = client.get("/api/projects/no-such-project/versions")
    assert resp.status_code == 404


# ── GET /api/versions/{id} ────────────────────────────────────────────────────


def test_get_version_detail_no_artifacts(client, version_id):
    """Version detail with no artifacts returns empty artifacts list."""
    resp = client.get(f"/api/versions/{version_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version_id"] == version_id
    assert body["name"] == "v1.0"
    assert body["artifacts"] == []
    assert body["error"] is None


def test_get_version_detail_with_artifact(client, project_id, version_id, artifact_id, db_conn):
    """Version detail includes artifacts with is_active field when nodes linked."""
    import asyncio
    # Link the artifact to the version
    asyncio.get_event_loop().run_until_complete(db_conn.execute(
        "UPDATE nodes SET version_id = ? WHERE id = ?",
        (version_id, artifact_id),
    ))
    asyncio.get_event_loop().run_until_complete(db_conn.commit())

    resp = client.get(f"/api/versions/{version_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["artifacts"]) == 1
    art = body["artifacts"][0]
    assert art["artifact_id"] == artifact_id
    assert "is_active" in art
    assert isinstance(art["is_active"], bool)
    assert isinstance(art["tags"], list)


def test_get_version_unknown_id_404(client):
    """Returns 404 for unknown version_id."""
    resp = client.get("/api/versions/no-such-version")
    assert resp.status_code == 404


# ── POST /api/versions ────────────────────────────────────────────────────────


def test_create_version_success(client, project_id, artifact_id):
    """POST /api/versions creates version, associates artifacts, returns 201."""
    payload = {
        "project_id": project_id,
        "version_name": "v2.0",
        "artifact_ids": [artifact_id],
    }
    resp = client.post("/api/versions", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "v2.0"
    assert body["artifact_count"] == 1
    assert "version_id" in body
    assert "created_at" in body
    assert body["error"] is None


def test_create_version_artifact_linked(client, project_id, artifact_id):
    """After POST /api/versions, the artifact appears in GET /api/versions/{id}."""
    resp = client.post("/api/versions", json={
        "project_id": project_id,
        "version_name": "v3.0",
        "artifact_ids": [artifact_id],
    })
    version_id = resp.json()["version_id"]
    detail = client.get(f"/api/versions/{version_id}")
    arts = detail.json()["artifacts"]
    assert any(a["artifact_id"] == artifact_id for a in arts)


def test_create_version_empty_artifact_ids_returns_422(client, project_id):
    """POST /api/versions with empty artifact_ids returns 422."""
    payload = {
        "project_id": project_id,
        "version_name": "Empty Version",
        "artifact_ids": [],
    }
    resp = client.post("/api/versions", json=payload)
    assert resp.status_code == 422


def test_create_version_unknown_project_returns_404(client):
    """POST /api/versions with unknown project_id returns 404."""
    payload = {
        "project_id": "no-such-project",
        "version_name": "Orphan",
        "artifact_ids": ["some-id"],
    }
    resp = client.post("/api/versions", json=payload)
    assert resp.status_code == 404


def test_create_version_unknown_artifact_returns_422(client, project_id):
    """POST /api/versions with an artifact_id that doesn't exist returns 422."""
    payload = {
        "project_id": project_id,
        "version_name": "Bad Artifact",
        "artifact_ids": ["totally-fake-artifact-id"],
    }
    resp = client.post("/api/versions", json=payload)
    assert resp.status_code == 422


def test_create_version_appears_in_project_list(client, project_id, artifact_id):
    """Newly created version appears in GET /api/projects/{id}/versions."""
    client.post("/api/versions", json={
        "project_id": project_id,
        "version_name": "v-new",
        "artifact_ids": [artifact_id],
    })
    resp = client.get(f"/api/projects/{project_id}/versions")
    names = [v["name"] for v in resp.json()["versions"]]
    assert "v-new" in names
