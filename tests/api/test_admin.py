"""
tests/api/test_admin.py

5.7 — Admin endpoint contract tests.

Covers:
- GET /api/admin/config returns masked key statuses (never raw values)
- POST /api/admin/config field="api_key" stores key server-side
- GET /api/admin/config after key save shows status "set"
- POST /api/admin/config field="threshold" updates threshold value
- GET /api/admin/health returns provider connectivity status
"""

from __future__ import annotations

_KEY_STATUSES = {"set", "not_set"}
_CONNECTIVITY_STATUSES = {"configured", "not_set"}


# ── GET /api/admin/health ─────────────────────────────────────────────────────


def test_health_returns_provider_statuses(client):
    """Health response includes all four provider connectivity fields."""
    resp = client.get("/api/admin/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    providers = body["providers"]
    for name in ("groq", "openrouter", "gemini", "ollama"):
        assert name in providers
        assert providers[name] in _CONNECTIVITY_STATUSES


def test_health_last_run_field(client):
    """Health response always contains last_run (may be null on fresh start)."""
    body = client.get("/api/admin/health").json()
    assert "last_run" in body


def test_health_ollama_configured_by_default(client):
    """Ollama shows 'configured' by default since ollama_url has a default value."""
    providers = client.get("/api/admin/health").json()["providers"]
    # Default URL is set so ollama should be configured
    assert providers["ollama"] == "configured"


def test_health_groq_not_set_without_env_key(client, monkeypatch):
    """Groq shows 'not_set' when no GROQ_API_KEY is in environment."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    # Config store was already init'd at app startup; check its state directly
    store = client.app.state.config_store
    store._keys["groq"] = None
    resp = client.get("/api/admin/health")
    assert resp.json()["providers"]["groq"] == "not_set"


# ── GET /api/admin/config ─────────────────────────────────────────────────────


def test_config_returns_masked_statuses(client):
    """GET /api/admin/config returns key statuses, never raw key values."""
    resp = client.get("/api/admin/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    providers = body["providers"]
    for name in ("groq", "openrouter", "gemini"):
        assert name in providers
        assert providers[name] in _KEY_STATUSES
        # Raw keys must never appear in the response
        assert providers[name] not in ("sk-", "gsk_")


def test_config_returns_thresholds(client):
    """GET /api/admin/config returns threshold dict."""
    body = client.get("/api/admin/config").json()
    thresholds = body["thresholds"]
    assert isinstance(thresholds, dict)
    for key in ("risk", "constraint", "dependency"):
        assert key in thresholds
        assert isinstance(thresholds[key], float)


def test_config_returns_ollama_url(client):
    """GET /api/admin/config returns ollama_url string."""
    body = client.get("/api/admin/config").json()
    assert isinstance(body["ollama_url"], str)
    assert body["ollama_url"]  # not empty


def test_config_returns_max_active_projects(client):
    """GET /api/admin/config returns max_active_projects int."""
    body = client.get("/api/admin/config").json()
    assert isinstance(body["max_active_projects"], int)
    assert body["max_active_projects"] > 0


# ── POST /api/admin/config — api_key ─────────────────────────────────────────


def test_save_api_key_returns_saved(client):
    """POST /api/admin/config field='api_key' returns status='saved'."""
    resp = client.post("/api/admin/config", json={
        "field": "api_key",
        "provider": "groq",
        "key": "gsk_test_key_value",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["field"] == "api_key"
    assert body["status"] == "saved"
    assert body["error"] is None


def test_save_api_key_shows_set_status(client):
    """After saving a key, GET /api/admin/config shows status='set' for that provider."""
    client.post("/api/admin/config", json={
        "field": "api_key",
        "provider": "groq",
        "key": "gsk_test_key_value",
    })
    body = client.get("/api/admin/config").json()
    assert body["providers"]["groq"] == "set"


def test_save_api_key_raw_value_not_in_config_response(client):
    """Raw key value must never appear in GET /api/admin/config response."""
    client.post("/api/admin/config", json={
        "field": "api_key",
        "provider": "openrouter",
        "key": "sk-or-secret-123",
    })
    config_text = client.get("/api/admin/config").text
    assert "sk-or-secret-123" not in config_text


def test_save_api_key_missing_provider_returns_422(client):
    """POST /api/admin/config field='api_key' without provider returns 422."""
    resp = client.post("/api/admin/config", json={
        "field": "api_key",
        "key": "some-key",
    })
    assert resp.status_code == 422


def test_save_api_key_invalid_provider_returns_422(client):
    """POST /api/admin/config with unsupported provider returns 422."""
    resp = client.post("/api/admin/config", json={
        "field": "api_key",
        "provider": "unknown-provider",
        "key": "some-key",
    })
    assert resp.status_code == 422


# ── POST /api/admin/config — threshold ───────────────────────────────────────


def test_save_threshold_returns_saved(client):
    """POST /api/admin/config field='threshold' returns status='saved'."""
    resp = client.post("/api/admin/config", json={
        "field": "threshold",
        "threshold_name": "risk",
        "threshold_value": 0.85,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["field"] == "threshold"
    assert body["status"] == "saved"
    assert body["error"] is None


def test_save_threshold_reflected_in_config(client):
    """After saving, GET /api/admin/config shows the updated threshold value."""
    client.post("/api/admin/config", json={
        "field": "threshold",
        "threshold_name": "risk",
        "threshold_value": 0.9,
    })
    body = client.get("/api/admin/config").json()
    assert body["thresholds"]["risk"] == pytest.approx(0.9)


def test_save_threshold_missing_name_returns_422(client):
    """POST /api/admin/config field='threshold' without threshold_name returns 422."""
    resp = client.post("/api/admin/config", json={
        "field": "threshold",
        "threshold_value": 0.5,
    })
    assert resp.status_code == 422


def test_save_threshold_invalid_name_returns_422(client):
    """Unsupported threshold_name returns 422."""
    resp = client.post("/api/admin/config", json={
        "field": "threshold",
        "threshold_name": "made_up_dimension",
        "threshold_value": 0.5,
    })
    assert resp.status_code == 422


def test_save_threshold_out_of_range_returns_422(client):
    """threshold_value outside [0.0, 1.0] returns 422."""
    resp = client.post("/api/admin/config", json={
        "field": "threshold",
        "threshold_name": "risk",
        "threshold_value": 1.5,
    })
    assert resp.status_code == 422


# ── POST /api/admin/config — ollama_url ──────────────────────────────────────


def test_save_ollama_url(client):
    """POST /api/admin/config field='ollama_url' saves and reflects the new URL."""
    resp = client.post("/api/admin/config", json={
        "field": "ollama_url",
        "ollama_url": "http://custom-ollama:11434",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    config = client.get("/api/admin/config").json()
    assert config["ollama_url"] == "http://custom-ollama:11434"


def test_save_invalid_field_returns_422(client):
    """POST /api/admin/config with unknown field value returns 422."""
    resp = client.post("/api/admin/config", json={"field": "nonsense"})
    assert resp.status_code == 422


# Need pytest.approx — import at module level
import pytest
