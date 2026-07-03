"""
contexta/api/config_store.py — In-process mutable configuration store.

Holds provider API keys, Ollama URL, gate thresholds, and project limits.
Keys are stored in memory only — they are never written to the SQLite DB.
On startup, values are read from environment variables when present.

This avoids leaking raw key values via the API: GET /api/admin/config
returns "set" / "not_set" status strings, never the actual key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Optional


_PROVIDER_ENV: Dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

_DEFAULT_THRESHOLDS: Dict[str, float] = {
    "risk": 0.7,
    "constraint": 0.7,
    "dependency": 0.7,
}


@dataclass
class AdminConfigStore:
    """Mutable runtime configuration for the API layer."""

    # Provider API keys — None means "not set"
    _keys: Dict[str, Optional[str]] = field(default_factory=dict)
    ollama_url: str = "http://localhost:11434"
    thresholds: Dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_THRESHOLDS))
    max_active_projects: int = 10
    last_run: Optional[str] = None

    def __post_init__(self) -> None:
        # Seed from environment variables so container config is honoured.
        for provider, env_var in _PROVIDER_ENV.items():
            val = os.environ.get(env_var)
            self._keys[provider] = val if val else None
        ollama_env = os.environ.get("OLLAMA_BASE_URL")
        if ollama_env:
            self.ollama_url = ollama_env

    # ── Key management ────────────────────────────────────────────────────────

    def set_key(self, provider: str, key: str) -> None:
        """Store a provider API key.  Empty string is treated as clearing the key."""
        self._keys[provider] = key if key.strip() else None

    def key_status(self, provider: str) -> str:
        """Return "set" if a non-empty key exists, else "not_set"."""
        return "set" if self._keys.get(provider) else "not_set"

    def provider_connectivity_status(self, provider: str) -> str:
        """Return "configured" if a non-empty key/url exists, else "not_set"."""
        if provider == "ollama":
            return "configured" if self.ollama_url else "not_set"
        return "configured" if self._keys.get(provider) else "not_set"

    def get_key(self, provider: str) -> Optional[str]:
        """Return the raw key value (used internally for LLM calls only)."""
        return self._keys.get(provider)

    # ── Thresholds ────────────────────────────────────────────────────────────

    def set_threshold(self, name: str, value: float) -> None:
        self.thresholds[name] = value

    def get_threshold(self, name: str) -> Optional[float]:
        return self.thresholds.get(name)
