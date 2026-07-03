"""
contexta/api/config_keys.py — Centralised app_config key constants.

Single source of truth for the string keys used in the ``app_config``
key/value table.  Shared by ``routers/admin.py`` (reads/writes) and
``pipeline_bridge.py`` (reads, to resolve an ``LLMConfig`` for pipeline runs).
"""

from __future__ import annotations

KEY_GROQ = "api_key_groq"
KEY_OPENROUTER = "api_key_openrouter"
KEY_GEMINI = "api_key_gemini"
KEY_OLLAMA_URL = "ollama_url"
KEY_THRESHOLD_RISK = "threshold_risk"
KEY_THRESHOLD_CONSTRAINT = "threshold_constraint"
KEY_THRESHOLD_DEPENDENCY = "threshold_dependency"
KEY_MAX_ACTIVE_PROJECTS = "max_active_projects"

# provider name (as surfaced in AdminConfigResponse.providers) → app_config key
PROVIDER_KEYS: dict[str, str] = {
    "groq": KEY_GROQ,
    "openrouter": KEY_OPENROUTER,
    "gemini": KEY_GEMINI,
}
