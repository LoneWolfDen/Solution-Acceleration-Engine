"""Milestone 5.3 — tests/api/test_artifacts.py

Tests:
  - GET /api/projects/{id}/artifacts returns is_active: bool on every artifact
  - POST /api/artifacts source="paste" creates artifact with correct tags
  - POST /api/artifacts source="url" creates artifact with url reference
  - PATCH /api/artifacts/{id} {active: false} sets is_active to false
  - GET /api/artifacts/suggestions returns string list; no LLM calls made
  - DELETE /api/artifacts/{id} removes the artifact
"""

from __future__ import annotations

import pytest

from .conftest import seed_artifact, seed_project


@pytest.mark.asyncio
async def test_list_artifacts_is_active_field(client, mem_db):
    """Every artifact row has an explicit boolean is_active field."""
    pid = await seed_project(mem_db)
    await seed_artifact(mem_db, pid, "Active Doc", is_active=True)
    await seed_artifact(mem_db, pid, "Inactive Doc", is_active=False)

    resp = await client.get(f"/api/projects/{pid}/artifacts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert len(body["artifacts"]) == 2

    for art in body["artifacts"]:
        assert isinstance(art["is_active"], bool)
        assert "artifact_id" in art
        assert "title" in art
        assert "tags" in art


@pytest.mark.asyncio
async def test_list_artifacts_is_active_values_correct(client, mem_db):
    """is_active values reflect what was stored."""
    pid = await seed_project(mem_db)
    await seed_artifact(mem_db, pid, "On", is_active=True)
    await seed_artifact(mem_db, pid, "Off", is_active=False)

    resp = await client.get(f"/api/projects/{pid}/artifacts")
    arts = {a["title"]: a["is_active"] for a in resp.json()["artifacts"]}
    assert arts["On"] is True
    assert arts["Off"] is False


@pytest.mark.asyncio
async def test_create_artifact_paste(client, mem_db):
    """POST source=paste creates artifact and returns correct tags."""
    pid = await seed_project(mem_db)

    resp = await client.post(
        "/api/artifacts",
        json={
            "source": "paste",
            "title": "Risk Register v1",
            "project_id": pid,
            "content": "This document lists all known project risks.",
            "tags": ["risk", "planning"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["title"] == "Risk Register v1"
    assert body["tags"] == ["risk", "planning"]
    assert body["is_active"] is True
    assert "artifact_id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_artifact_url(client, mem_db):
    """POST source=url creates artifact with url reference."""
    pid = await seed_project(mem_db)

    resp = await client.post(
        "/api/artifacts",
        json={
            "source": "url",
            "title": "Architecture Diagram",
            "project_id": pid,
            "url": "https://example.com/arch.pdf",
            "tags": ["architecture"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["title"] == "Architecture Diagram"


@pytest.mark.asyncio
async def test_create_artifact_paste_missing_content_returns_422(client, mem_db):
    """source=paste without content returns 422 with error information."""
    pid = await seed_project(mem_db)

    resp = await client.post(
        "/api/artifacts",
        json={
            "source": "paste",
            "title": "No Content",
            "project_id": pid,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_artifact_url_missing_url_returns_422(client, mem_db):
    """source=url without url returns 422."""
    pid = await seed_project(mem_db)

    resp = await client.post(
        "/api/artifacts",
        json={
            "source": "url",
            "title": "Missing URL",
            "project_id": pid,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_artifact_deactivate(client, mem_db):
    """PATCH {active: false} sets is_active to False."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid, is_active=True)

    resp = await client.patch(f"/api/artifacts/{aid}", json={"active": False})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_active"] is False
    assert body["artifact_id"] == aid
    assert body["error"] is None


@pytest.mark.asyncio
async def test_patch_artifact_activate(client, mem_db):
    """PATCH {active: true} sets is_active to True."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid, is_active=False)

    resp = await client.patch(f"/api/artifacts/{aid}", json={"active": True})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


@pytest.mark.asyncio
async def test_patch_artifact_unknown_returns_404(client, mem_db):
    """PATCH on unknown artifact returns 404."""
    resp = await client.patch("/api/artifacts/unknown-id", json={"active": False})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_artifact(client, mem_db):
    """DELETE removes the artifact and returns status=deleted."""
    pid = await seed_project(mem_db)
    aid = await seed_artifact(mem_db, pid)

    resp = await client.delete(f"/api/artifacts/{aid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "deleted"
    assert body["artifact_id"] == aid
    assert body["error"] is None

    # Confirm gone.
    cursor = await mem_db.execute("SELECT id FROM artifacts WHERE id = ?", (aid,))
    assert await cursor.fetchone() is None


@pytest.mark.asyncio
async def test_delete_artifact_unknown_returns_404(client, mem_db):
    """DELETE on unknown artifact returns 404."""
    resp = await client.delete("/api/artifacts/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_suggestions_returns_string_list(client, mem_db):
    """GET /api/artifacts/suggestions returns a list of strings."""
    resp = await client.get(
        "/api/artifacts/suggestions",
        params={"filename": "risk_register.md", "content_preview": "project risks"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert isinstance(body["suggestions"], list)
    for s in body["suggestions"]:
        assert isinstance(s, str)


@pytest.mark.asyncio
async def test_suggestions_no_llm_call(client, mem_db, monkeypatch):
    """Suggestions endpoint never calls litellm.acompletion."""
    import litellm

    called = []
    monkeypatch.setattr(
        litellm,
        "acompletion",
        lambda *a, **kw: called.append(True),
    )

    await client.get(
        "/api/artifacts/suggestions",
        params={"filename": "scope.md", "content_preview": "statement of work"},
    )
    assert called == [], "litellm.acompletion must not be called by suggestions endpoint"


@pytest.mark.asyncio
async def test_suggestions_architecture_tag(client, mem_db):
    """Filename containing 'architecture' surfaces the architecture tag."""
    resp = await client.get(
        "/api/artifacts/suggestions",
        params={"filename": "technical_architecture.md", "content_preview": ""},
    )
    suggestions = resp.json()["suggestions"]
    assert "architecture" in suggestions


@pytest.mark.asyncio
async def test_suggestions_empty_inputs(client, mem_db):
    """Empty filename and content_preview returns empty suggestions list."""
    resp = await client.get(
        "/api/artifacts/suggestions",
        params={"filename": "", "content_preview": ""},
    )
    assert resp.status_code == 200
    assert resp.json()["suggestions"] == []
