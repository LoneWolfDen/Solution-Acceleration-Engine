"""
contexta/api/config.py — Minimal configuration for the Web API layer.

Intentionally separate from ContextaConfig (which requires CONTEXTA_LLM_BACKEND).
The API server can start with no LLM configuration — users set providers via
the Admin Dashboard, which writes values to the app_config DB table.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class WebAPIConfig(BaseSettings):
    """
    Minimal settings needed to boot the FastAPI server.

    Only db_path and log_level are required at startup.
    LLM provider keys are stored in the app_config DB table and managed
    at runtime through the Admin Dashboard.
    """

    model_config = SettingsConfigDict(
        env_prefix="CONTEXTA_",
        case_sensitive=False,
        extra="ignore",
    )

    db_path: str = "/data/contexta.db"
    log_level: str = "INFO"


def load_api_config() -> WebAPIConfig:
    """Load and return the web API configuration from environment variables."""
    return WebAPIConfig()
