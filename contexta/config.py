"""
contexta/config.py — Environment variable parsing and application configuration.

All required variables are validated at startup. Missing or malformed values
raise ConfigError immediately so the TUI can display a fatal error and halt.
"""

from __future__ import annotations

from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    """Raised when environment configuration is invalid or incomplete."""


class ContextaConfig(BaseSettings):
    """
    Application configuration loaded exclusively from environment variables.

    Required:
        CONTEXTA_LLM_BACKEND  — LiteLLM-compatible backend in 'provider/model' format.

    Optional (have defaults):
        CONTEXTA_DB_PATH       — Path to the SQLite database file.
        CONTEXTA_EXPORT_PATH   — Default directory for JSON packet exports.
        CONTEXTA_LLM_API_KEY   — API key for hosted LLM backends.
        CONTEXTA_LLM_BASE_URL  — Override base URL (e.g. for local Ollama).
        CONTEXTA_LOG_LEVEL     — Logging verbosity level.
        CONTEXTA_EXECUTION_MODE — Pipeline execution mode; MVP default is UNIFIED.
    """

    model_config = SettingsConfigDict(
        env_prefix="CONTEXTA_",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Required ─────────────────────────────────────────────────────────────
    llm_backend: str  # CONTEXTA_LLM_BACKEND

    # ── Optional with defaults ────────────────────────────────────────────────

    db_path: str = "/data/contexta.db"       # CONTEXTA_DB_PATH
    export_path: str = "/exports"            # CONTEXTA_EXPORT_PATH
    llm_api_key: Optional[str] = None        # CONTEXTA_LLM_API_KEY
    llm_base_url: Optional[str] = None       # CONTEXTA_LLM_BASE_URL
    log_level: str = "WARNING"               # CONTEXTA_LOG_LEVEL

    # ── Unified Toggle — MVP configuration path ───────────────────────────────
    execution_mode: str = "UNIFIED"          # CONTEXTA_EXECUTION_MODE

    # ── Rate limiting ─────────────────────────────────────────────────────────
    llm_request_delay_seconds: float = 2.5   # CONTEXTA_LLM_REQUEST_DELAY_SECONDS

    @field_validator("llm_backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """
        Enforce 'provider/model' format for LiteLLM backend identifiers.

        Examples of valid values: 'ollama/mistral', 'openai/gpt-4o',
        'anthropic/claude-3-haiku'.  A bare model name such as 'mistral'
        is rejected because LiteLLM requires the provider prefix to route
        the request correctly.
        """
        v = v.strip()
        if not v:
            raise ValueError("CONTEXTA_LLM_BACKEND must not be empty.")
        if "/" not in v:
            raise ValueError(
                f"CONTEXTA_LLM_BACKEND must be in 'provider/model' format, got: {v!r}. "
                "Example: 'ollama/mistral' or 'openai/gpt-4o'."
            )
        provider, _, model = v.partition("/")
        if not provider.strip():
            raise ValueError(
                f"CONTEXTA_LLM_BACKEND provider part is empty in: {v!r}."
            )
        if not model.strip():
            raise ValueError(
                f"CONTEXTA_LLM_BACKEND model part is empty in: {v!r}."
            )
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(
                f"CONTEXTA_LOG_LEVEL must be one of {sorted(allowed)}, got: {v!r}."
            )
        return upper

    @field_validator("execution_mode")
    @classmethod
    def validate_execution_mode(cls, v: str) -> str:
        allowed = {"UNIFIED"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(
                f"CONTEXTA_EXECUTION_MODE must be one of {sorted(allowed)}, got: {v!r}. "
                "Only UNIFIED is supported in the MVP."
            )
        return upper


def load_config() -> ContextaConfig:
    """
    Load and validate application configuration from environment variables.

    Raises:
        ConfigError: if any required variable is missing or any value fails
                     validation.  The message is human-readable and suitable
                     for display in the TUI fatal-error overlay.
    """
    try:
        return ContextaConfig()  # type: ignore[call-arg]
    except Exception as exc:
        raise ConfigError(f"Configuration error: {exc}") from exc
