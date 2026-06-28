"""
tests/api/test_admin.py — Admin config, health, and key masking.
"""

import pytest


def test_get_admin_health_shape(test_app):
    resp = test_app.get("/api/admin/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert "groq" in data["providers"]
    assert "openrouter" in data["providers"]
    assert "gemini" in data["providers"]
    assert "ollama" in data["providers"]
    assert data.get("error") is None


def test_get_admin_config_shape(test_app):
    resp = test_app.get("/api/admin/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert "thresholds" in data
    assert "ollama_url" in data
    assert "max_active_projects" in data
    assert data.get("error") is None


def test_save_api_key_then_check_status(test_app):
    # Save a groq key
    resp = test_app.post(
        "/api/admin/config",
        json={"field": "api_key", "provider": "groq", "key": "gsk_test_key"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"
    assert resp.json().get("error") is None

    # Config should now show "set" for groq — never the raw value
    config_resp = test_app.get("/api/admin/config")
    assert config_resp.json()["providers"]["groq"] == "set"


def test_raw_api_key_never_returned(test_app):
    """Ensure the raw key value is never present in any response."""
    raw_key = "sk_secret_value_must_not_appear"
    test_app.post(
        "/api/admin/config",
        json={"field": "api_key", "provider": "openrouter", "key": raw_key},
    )
    resp = test_app.get("/api/admin/config")
    resp_text = resp.text
    assert raw_key not in resp_text


def test_save_threshold(test_app):
    resp = test_app.post(
        "/api/admin/config",
        json={"field": "threshold", "threshold_name": "risk", "threshold_value": 0.80},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    config = test_app.get("/api/admin/config").json()
    assert abs(config["thresholds"]["risk"] - 0.80) < 0.001


def test_save_config_invalid_field_returns_422(test_app):
    resp = test_app.post(
        "/api/admin/config",
        json={"field": "unknown_field"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] is not None
