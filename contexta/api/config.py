"""
contexta/api/config.py — Minimal configuration for the Web API layer.

Intentionally separate from ContextaConfig (which requires CONTEXTA_LLM_BACKEND).
The API server can start with no LLM configuration — users set providers via
the Admin Dashboard, which writes values to the app_config DB table.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Must match the default computed in contexta/api/__init__.py exactly.
# Background tasks (contexta/api/pipeline_bridge.py) call
# load_api_config().db_path to open their own aiosqlite connection — if this
# default ever drifts from the one used by the main app's lifespan, review
# and proposal jobs are written to a different database than the one the
# background task reads from, so they silently never progress past "queued"
# (see git history for the incident this comment documents).
_PROJECT_ROOT: Path = Path(__file__).parents[2]
_DEFAULT_DB_PATH: str = str(_PROJECT_ROOT / "data" / "contexta.db")


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

    db_path: str = _DEFAULT_DB_PATH
    log_level: str = "INFO"


def load_api_config() -> WebAPIConfig:
    """Load and return the web API configuration from environment variables."""
    return WebAPIConfig()
