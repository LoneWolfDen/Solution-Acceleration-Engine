"""
contexta/api/config.py — Minimal configuration for the Web API layer.

Intentionally separate from ContextaConfig (which requires CONTEXTA_LLM_BACKEND).
The API server can start with no LLM configuration — users set providers via
the Admin Dashboard, which writes values to the app_config DB table.

DB PATH CONTRACT
----------------
The canonical database file is ``contexta.db`` at the project root — the same
path used by ``rxconfig.py`` (``db_url="sqlite:///contexta.db"``).

Override at runtime by setting ``CONTEXTA_DB_PATH`` in your ``.env`` file, e.g.:
    CONTEXTA_DB_PATH=/app/data/contexta.db   # Docker / production

Background tasks (``pipeline_bridge.py``) call ``load_api_config().db_path``
to open their own aiosqlite connections.  If this default ever drifts from the
path used by the lifespan hook in ``contexta/api/__init__.py``, review and
proposal jobs silently stall at "queued" (see git history for the incident).
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels up from this file (contexta/api/config.py)
_PROJECT_ROOT: Path = Path(__file__).parents[2]

# Default: root-level contexta.db, matching rxconfig.py's db_url.
# Can be overridden by CONTEXTA_DB_PATH env var (e.g. for Docker).
_DEFAULT_DB_PATH: str = str(_PROJECT_ROOT / "contexta.db")


class WebAPIConfig(BaseSettings):
    """
    Minimal settings needed to boot the FastAPI server.

    Only ``db_path`` and ``log_level`` are required at startup.
    LLM provider keys are stored in the ``app_config`` DB table and managed
    at runtime through the Admin Dashboard.

    Environment variables (all optional):
        CONTEXTA_DB_PATH   — absolute path to the SQLite file
                             default: <project_root>/contexta.db
        CONTEXTA_LOG_LEVEL — Python logging level
                             default: INFO
    """

    model_config = SettingsConfigDict(
        env_prefix="CONTEXTA_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    db_path: str = _DEFAULT_DB_PATH
    log_level: str = "INFO"


def load_api_config() -> WebAPIConfig:
    """Load and return the web API configuration from environment / .env file."""
    return WebAPIConfig()
