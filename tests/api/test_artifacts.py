"""
tests/api/test_artifacts.py

5.3 — Artifact endpoint contract tests.

Covers:
- GET /api/projects/{id}/artifacts returns is_active: bool on every artifact
- POST /api/artifacts source="paste" creates artifact with correct tags
- POST /api/artifacts source="upload" creates artifact from file bytes (content field)
- POST /api/artifacts source="url" creates artifact with url reference
- PATCH /api/artifacts/{id} {active: false} sets is_active to false
- GET /api/artifacts/suggestions returns string list; no LLM calls made
"""

from __future__ import annotations


# ── GET /api/projects/{id}/artifacts ─────────────────────────────────────────


def test_list_artifacts_is_active_field_present(client, project_id, artifact_id):
    """Every artifact in the list has an explicit is_active bool field."""
    resp = client.get(f"/api/projects/{project_id}/artifacts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert len(body["artifacts"]) == 1
    art = body["artifacts"][0]
    assert "is_active" in art
    assert isinstance(art["is_active"], bool)


def test_list_artifacts_required_fields(client, project_id, artifact_id):
    """Each artifact summary contains all required fields."""
    resp = client.get(f"/api/projects/{project_id}/artifacts")
    art = resp.json()["artifacts"][0]
    assert art["artifact_id"] == artifact_id
    assert art["title"] == "Test Artifact"
    assert isinstance(art["tags"], list)
    assert isinstance(art["is_active"], bool)
    assert "created_at" in art


def test_list_artifacts_empty(client, project_id):
    """Returns empty list when project has no artifacts."""
    resp = client.get(f"/api/projects/{project_id}/artifacts")
    assert resp.status_code == 200
    assert resp.json()["artifacts"] == []


def test_list_artifacts_unknown_project_404(client):
    """Returns 404 for unknown project."""
    resp = client.get("/api/projects/no-such-project/artifacts")
    assert resp.status_code == 404


# ── POST /api/artifacts ───────────────────────────────────────────────────────


def test_create_artifact_paste(client, project_id):
    """source='paste' creates artifact; tags and is_active are returned."""
    payload = {
        "source": "paste",
        "title": "My Pasted Doc",
        "project_id": project_id,
        "content": "Some text content here",
        "tags": ["sow", "finance"],
    }
    resp = client.post("/api/artifacts", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["title"] == "My Pasted Doc"
    assert body["tags"] == ["sow", "finance"]
    assert body["is_active"] is True
    assert "artifact_id" in body
    assert "created_at" in body


def test_create_artifact_paste_appears_in_list(client, project_id):
    """Artifact created via paste appears in GET /api/projects/{id}/artifacts."""
    client.post("/api/artifacts", json={
        "source": "paste",
        "title": "Listed Doc",
        "project_id": project_id,
        "content": "content",
        "tags": [],
    })
    resp = client.get(f"/api/projects/{project_id}/artifacts")
    titles = [a["title"] for a in resp.json()["artifacts"]]
    assert "Listed Doc" in titles


def test_create_artifact_upload(client, project_id):
    """source='upload' with content field stores the artifact correctly."""
    payload = {
        "source": "upload",
        "title": "Uploaded File",
        "project_id": project_id,
        "content": "binary-like content string",
        "tags": ["document"],
    }
    resp = client.post("/api/artifacts", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Uploaded File"
    assert body["tags"] == ["document"]
    assert body["error"] is None


def test_create_artifact_url(client, project_id):
    """source='url' creates artifact with url reference."""
    payload = {
        "source": "url",
        "title": "External Doc",
        "project_id": project_id,
        "url": "https://example.com/proposal.pdf",
        "tags": ["proposal"],
    }
    resp = client.post("/api/artifacts", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "External Doc"
    assert body["tags"] == ["proposal"]
    assert body["error"] is None


def test_create_artifact_url_missing_url_returns_422(client, project_id):
    """source='url' without a url field returns 422."""
    payload = {
        "source": "url",
        "title": "Missing URL",
        "project_id": project_id,
        "tags": [],
    }
    resp = client.post("/api/artifacts", json=payload)
    assert resp.status_code == 422


def test_create_artifact_paste_missing_content_returns_422(client, project_id):
    """source='paste' without content returns 422."""
    payload = {
        "source": "paste",
        "title": "No Content",
        "project_id": project_id,
        "tags": [],
    }
    resp = client.post("/api/artifacts", json=payload)
    assert resp.status_code == 422


def test_create_artifact_invalid_source_returns_422(client, project_id):
    """Unknown source value returns 422."""
    payload = {
        "source": "telepathy",
        "title": "Telepathic Doc",
        "project_id": project_id,
        "content": "stuff",
        "tags": [],
    }
    resp = client.post("/api/artifacts", json=payload)
    assert resp.status_code == 422


def test_create_artifact_empty_title_returns_422(client, project_id):
    """Empty title returns 422."""
    payload = {
        "source": "paste",
        "title": "   ",
        "project_id": project_id,
        "content": "stuff",
        "tags": [],
    }
    resp = client.post("/api/artifacts", json=payload)
    assert resp.status_code == 422


def test_create_artifact_unknown_project_returns_404(client):
    """Creating artifact for unknown project returns 404."""
    payload = {
        "source": "paste",
        "title": "Orphan",
        "project_id": "no-such-project",
        "content": "content",
        "tags": [],
    }
    resp = client.post("/api/artifacts", json=payload)
    assert resp.status_code == 404


# ── PATCH /api/artifacts/{id} ────────────────────────────────────────────────


def test_patch_artifact_set_inactive(client, project_id, artifact_id):
    """PATCH {active: false} sets is_active to false."""
    resp = client.patch(f"/api/artifacts/{artifact_id}", json={"active": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["artifact_id"] == artifact_id
    assert body["is_active"] is False
    assert body["error"] is None


def test_patch_artifact_set_active(client, project_id, artifact_id):
    """PATCH {active: true} re-enables the artifact."""
    client.patch(f"/api/artifacts/{artifact_id}", json={"active": False})
    resp = client.patch(f"/api/artifacts/{artifact_id}", json={"active": True})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


def test_patch_artifact_reflects_in_list(client, project_id, artifact_id):
    """After PATCH, the list endpoint returns the updated is_active value."""
    client.patch(f"/api/artifacts/{artifact_id}", json={"active": False})
    resp = client.get(f"/api/projects/{project_id}/artifacts")
    arts = resp.json()["artifacts"]
    matching = [a for a in arts if a["artifact_id"] == artifact_id]
    assert len(matching) == 1
    assert matching[0]["is_active"] is False


def test_patch_artifact_unknown_id_returns_404(client):
    """PATCH on unknown artifact_id returns 404."""
    resp = client.patch("/api/artifacts/no-such-id", json={"active": False})
    assert resp.status_code == 404


# ── DELETE /api/artifacts/{id} ────────────────────────────────────────────────


def test_delete_artifact_success(client, project_id, artifact_id):
    """DELETE removes artifact and returns status=deleted."""
    resp = client.delete(f"/api/artifacts/{artifact_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["artifact_id"] == artifact_id
    assert body["status"] == "deleted"
    assert body["error"] is None


def test_delete_artifact_not_in_list_after_deletion(client, project_id, artifact_id):
    """Deleted artifact no longer appears in the artifact list."""
    client.delete(f"/api/artifacts/{artifact_id}")
    resp = client.get(f"/api/projects/{project_id}/artifacts")
    ids = [a["artifact_id"] for a in resp.json()["artifacts"]]
    assert artifact_id not in ids


def test_delete_artifact_unknown_id_returns_404(client):
    """DELETE on unknown artifact_id returns 404."""
    resp = client.delete("/api/artifacts/no-such-id")
    assert resp.status_code == 404


# ── GET /api/artifacts/suggestions ───────────────────────────────────────────


def test_suggestions_returns_list(client):
    """Returns a list of strings; no LLM calls made."""
    resp = client.get("/api/artifacts/suggestions?filename=proposal.md&content_preview=scope")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert isinstance(body["suggestions"], list)
    for s in body["suggestions"]:
        assert isinstance(s, str)


def test_suggestions_filename_md_tag(client):
    """A .md filename yields 'markdown' tag."""
    resp = client.get("/api/artifacts/suggestions?filename=architecture.md")
    assert "markdown" in resp.json()["suggestions"]


def test_suggestions_sow_keyword(client):
    """'statement of work' in content_preview yields 'sow' tag."""
    resp = client.get(
        "/api/artifacts/suggestions?filename=doc.txt&content_preview=statement+of+work"
    )
    assert "sow" in resp.json()["suggestions"]


def test_suggestions_empty_inputs(client):
    """Empty filename and content_preview returns empty list, not an error."""
    resp = client.get("/api/artifacts/suggestions")
    assert resp.status_code == 200
    assert resp.json()["error"] is None
    assert isinstance(resp.json()["suggestions"], list)


def test_suggestions_no_llm_calls(client, monkeypatch):
    """Suggestions endpoint never triggers litellm calls."""
    called = []

    def _fake_complete(*args, **kwargs):
        called.append(True)
        raise AssertionError("LLM must not be called from suggestions endpoint")

    monkeypatch.setattr("litellm.acompletion", _fake_complete, raising=False)
    resp = client.get("/api/artifacts/suggestions?filename=plan.md&content_preview=risk")
    assert resp.status_code == 200
    assert called == []
