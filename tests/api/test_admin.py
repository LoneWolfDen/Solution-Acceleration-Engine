"""tests/api/test_admin.py — Admin config, health, key masking."""

import pytest


def test_get_admin_health_shape(test_app):
    resp = test_app.get("/api/admin/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    for key in ("groq", "openrouter", "gemini", "ollama"):
        assert key in data["providers"]
    assert data.get("error") is None


def test_get_admin_config_shape(test_app):
    resp = test_app.get("/api/admin/config")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("providers", "thresholds", "ollama_url", "max_active_projects"):
        assert key in data
    assert data.get("error") is None


def test_save_api_key_then_check_status(test_app):
    resp = test_app.post("/api/admin/config", json={"field": "api_key", "provider": "groq", "key": "gsk_test"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"
    config = test_app.get("/api/admin/config").json()
    assert config["providers"]["groq"] == "set"


def test_raw_api_key_never_returned(test_app):
    raw = "sk_secret_must_not_appear"
    test_app.post("/api/admin/config", json={"field": "api_key", "provider": "openrouter", "key": raw})
    assert raw not in test_app.get("/api/admin/config").text


def test_save_threshold(test_app):
    resp = test_app.post("/api/admin/config", json={"field": "threshold", "threshold_name": "risk", "threshold_value": 0.80})
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"
    config = test_app.get("/api/admin/config").json()
    assert abs(config["thresholds"]["risk"] - 0.80) < 0.001


def test_save_config_invalid_field_returns_422(test_app):
    resp = test_app.post("/api/admin/config", json={"field": "unknown_field"})
    assert resp.status_code == 422
    assert resp.json()["error"] is not None
