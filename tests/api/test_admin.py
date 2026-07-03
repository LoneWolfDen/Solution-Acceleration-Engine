"""Milestone 5.7 — tests/api/test_admin.py

Tests:
  - GET /api/admin/config returns masked key statuses (never raw values)
  - POST /api/admin/config field="api_key" stores key server-side
  - GET /api/admin/config after key save shows status "set"
  - POST /api/admin/config field="threshold" updates threshold value
  - GET /api/admin/health returns provider connectivity status
  - Invalid field returns 422
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_returns_provider_status(client, mem_db):
    """GET /api/admin/health returns provider status dict and error=null."""
    resp = await client.get("/api/admin/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    providers = body["providers"]
    for key in ("groq", "openrouter", "gemini", "ollama"):
        assert key in providers
        assert providers[key] in ("configured", "not_set")


@pytest.mark.asyncio
async def test_health_last_run_null_when_no_reviews(client, mem_db):
    """last_run is null when no completed reviews exist."""
    resp = await client.get("/api/admin/health")
    assert resp.json()["last_run"] is None


@pytest.mark.asyncio
async def test_get_config_returns_masked_keys(client, mem_db):
    """GET /api/admin/config returns 'set' or 'not_set' — never raw key values."""
    resp = await client.get("/api/admin/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    for provider, status in body["providers"].items():
        assert status in ("set", "not_set"), (
            f"Provider '{provider}' returned raw key value: {status!r}"
        )


@pytest.mark.asyncio
async def test_get_config_returns_all_required_fields(client, mem_db):
    """GET /api/admin/config response includes all contract fields."""
    resp = await client.get("/api/admin/config")
    body = resp.json()
    assert "providers" in body
    assert "ollama_url" in body
    assert "thresholds" in body
    assert "max_active_projects" in body
    thresholds = body["thresholds"]
    assert "risk" in thresholds
    assert "constraint" in thresholds
    assert "dependency" in thresholds


@pytest.mark.asyncio
async def test_save_api_key_shows_set_after(client, mem_db):
    """POST api_key then GET config shows 'set' for that provider."""
    resp = await client.post(
        "/api/admin/config",
        json={"field": "api_key", "provider": "groq", "key": "gsk-test-key-value"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "saved"
    assert body["error"] is None

    config_resp = await client.get("/api/admin/config")
    assert config_resp.json()["providers"]["groq"] == "set"


@pytest.mark.asyncio
async def test_save_api_key_does_not_expose_raw_value(client, mem_db):
    """After saving an API key, GET /admin/config must not return the raw key."""
    raw_key = "gsk-super-secret-key-12345"
    await client.post(
        "/api/admin/config",
        json={"field": "api_key", "provider": "openrouter", "key": raw_key},
    )

    config_resp = await client.get("/api/admin/config")
    body_str = config_resp.text
    assert raw_key not in body_str, "Raw API key must never appear in config response"


@pytest.mark.asyncio
async def test_save_threshold_updates_value(client, mem_db):
    """POST threshold then GET config shows updated value."""
    resp = await client.post(
        "/api/admin/config",
        json={"field": "threshold", "threshold_name": "risk", "threshold_value": 0.85},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    config_resp = await client.get("/api/admin/config")
    assert config_resp.json()["thresholds"]["risk"] == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_save_ollama_url(client, mem_db):
    """POST ollama_url updates the stored URL."""
    resp = await client.post(
        "/api/admin/config",
        json={"field": "ollama_url", "ollama_url": "http://my-ollama:11434"},
    )
    assert resp.status_code == 200

    config_resp = await client.get("/api/admin/config")
    assert config_resp.json()["ollama_url"] == "http://my-ollama:11434"


@pytest.mark.asyncio
async def test_save_config_unknown_field_returns_422(client, mem_db):
    """POST with an unknown field value returns 422."""
    resp = await client.post(
        "/api/admin/config",
        json={"field": "unknown_field"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_save_api_key_missing_provider_returns_422(client, mem_db):
    """POST api_key without provider returns 422."""
    resp = await client.post(
        "/api/admin/config",
        json={"field": "api_key", "key": "some-key"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_save_threshold_invalid_name_returns_422(client, mem_db):
    """POST threshold with unknown threshold_name returns 422."""
    resp = await client.post(
        "/api/admin/config",
        json={"field": "threshold", "threshold_name": "invalid", "threshold_value": 0.5},
    )
    assert resp.status_code == 422
