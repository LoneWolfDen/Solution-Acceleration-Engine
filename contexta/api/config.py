"""
contexta/api/config.py — Environment variable parsing for the API server.

Reads the same CONTEXTA_* variables as the core ContextaConfig so the API
server can run using the existing environment without additional setup.
Only the subset of settings required by the API layer is declared here.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiConfig(BaseSettings):
    """
    Configuration for the FastAPI server, loaded from environment variables.

    Required:
        CONTEXTA_LLM_BACKEND  — passed through; not used by the API layer
                                directly but required so the shared DB init
                                path does not fail.

    Optional (have defaults):
        CONTEXTA_DB_PATH  — path to the SQLite database file.
    """

    model_config = SettingsConfigDict(
        env_prefix="CONTEXTA_",
        case_sensitive=False,
        extra="ignore",
    )

    # The API only needs the DB path to open the connection.
    db_path: str = "/data/contexta.db"   # CONTEXTA_DB_PATH


def load_api_config() -> ApiConfig:
    """Load and return API configuration from environment variables.

    Raises:
        ValidationError: if any required variable is missing or malformed.
    """
    return ApiConfig()
