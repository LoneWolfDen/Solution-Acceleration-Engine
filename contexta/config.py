"""Environment variable parsing and application configuration.

``ContextaConfig`` uses ``pydantic-settings`` to pull all required and optional
values from the process environment.  ``load_config()`` is the single entry
point called by ``__main__.py``; it raises ``ConfigError`` on any validation
failure so the startup path can surface a clear message before launching the
TUI.
"""

from __future__ import annotations

from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Exception ─────────────────────────────────────────────────────────────────


class ConfigError(Exception):
    """Raised when required environment variables are missing or invalid."""


# ── Settings model ────────────────────────────────────────────────────────────


class ContextaConfig(BaseSettings):
    """Application-wide configuration sourced from environment variables.

    All variables use the ``CONTEXTA_`` prefix.

    Required
    --------
    llm_backend:
        LiteLLM-compatible backend identifier, e.g. ``"ollama/mistral"``.
        Must contain a ``"/"`` separator.

    Optional (with defaults)
    ------------------------
    db_path:
        Path to the SQLite database file inside the container.
    export_path:
        Default directory for JSON packet exports.
    llm_api_key:
        API key for hosted backends (OpenAI, Anthropic, etc.).
    llm_base_url:
        Override base URL — required for Ollama.
    log_level:
        Python logging level string.
    """

    model_config = SettingsConfigDict(env_prefix="CONTEXTA_", case_sensitive=False)

    llm_backend: str
    db_path: str = "/data/contexta.db"
    export_path: str = "/exports"
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    log_level: str = "WARNING"

    @field_validator("llm_backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        if "/" not in v:
            raise ValueError(
                f"CONTEXTA_LLM_BACKEND must be in 'provider/model' format, got: {v!r}"
            )
        return v


# ── Public factory ────────────────────────────────────────────────────────────


def load_config() -> ContextaConfig:
    """Load and validate configuration from environment variables.

    Returns
    -------
    ContextaConfig
        Validated configuration instance.

    Raises
    ------
    ConfigError
        If any required variable is absent or any validator fails.
    """
    try:
        return ContextaConfig()  # type: ignore[call-arg]
    except Exception as exc:
        raise ConfigError(f"Configuration error: {exc}") from exc
