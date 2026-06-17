"""
tests/test_config.py — Property and unit tests for contexta/config.py.

Properties covered:
  Property 1: LiteLLM Backend String Acceptance
              Valid 'provider/model' strings are accepted; strings without '/'
              are rejected with ConfigError.
  Property 2: Missing Environment Variable Rejection
              Absence of CONTEXTA_LLM_BACKEND raises ConfigError.
"""

from __future__ import annotations

import os
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from unittest.mock import patch

from contexta.config import ConfigError, ContextaConfig, load_config


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_env(llm_backend: str, **extra: str) -> dict[str, str]:
    """Return an env dict with the minimum required variable set."""
    base = {"CONTEXTA_LLM_BACKEND": llm_backend}
    base.update({k.upper(): v for k, v in extra.items()})
    return base


def _load_with_env(env: dict[str, str]) -> ContextaConfig:
    """Patch os.environ to *only* the supplied dict, then call load_config()."""
    with patch.dict(os.environ, env, clear=True):
        return load_config()


# ─────────────────────────────────────────────────────────────────────────────
# Property 1 — LiteLLM Backend String Acceptance
# ─────────────────────────────────────────────────────────────────────────────

# Strategy: text that is safe to use as an env value, min 1 char each side
_identifier = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd"),
        whitelist_characters="-_.",
    ),
    min_size=1,
    max_size=32,
)

_valid_backend = st.builds(
    lambda p, m: f"{p}/{m}",
    _identifier,
    _identifier,
)

# Strings that do NOT contain '/' — must be rejected.
# blacklist_categories=('Cs',) excludes Unicode surrogate code points
# (U+D800–U+DFFF) which are not valid in UTF-8 and cause UnicodeEncodeError
# when passed to os.environ via patch.dict.
_invalid_backend = st.text(
    alphabet=st.characters(
        blacklist_characters="/\x00\n",
        blacklist_categories=("Cs",),
    ),
    min_size=1,
    max_size=64,
).filter(lambda s: s.strip() and "/" not in s)


@given(backend=_valid_backend)
@settings(max_examples=50)
def test_property1_valid_backend_accepted(backend: str) -> None:
    """
    Property 1a: Any 'provider/model' string (both sides non-empty) is accepted.
    """
    assume(backend.partition("/")[0].strip())   # provider non-empty
    assume(backend.partition("/")[2].strip())   # model non-empty

    cfg = _load_with_env({"CONTEXTA_LLM_BACKEND": backend})
    assert cfg.llm_backend == backend


@given(backend=_invalid_backend)
@settings(max_examples=50)
def test_property1_invalid_backend_rejected(backend: str) -> None:
    """
    Property 1b: Any string without '/' raises ConfigError.
    """
    with pytest.raises(ConfigError):
        _load_with_env({"CONTEXTA_LLM_BACKEND": backend})


# ─────────────────────────────────────────────────────────────────────────────
# Property 2 — Missing Environment Variable Rejection
# ─────────────────────────────────────────────────────────────────────────────

def test_property2_missing_llm_backend_raises_config_error() -> None:
    """
    Property 2: Absence of CONTEXTA_LLM_BACKEND raises ConfigError.
    CONTEXTA_LLM_BACKEND is the only *required* variable; all others have
    defaults, so clearing the environment is the minimum failing case.
    """
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ConfigError) as exc_info:
            load_config()
    # Message should be human-readable
    assert "Configuration error" in str(exc_info.value)


def test_property2_other_vars_absent_do_not_raise() -> None:
    """
    Optional variables missing from the environment must NOT raise ConfigError;
    only the required CONTEXTA_LLM_BACKEND must be present.
    """
    env = {"CONTEXTA_LLM_BACKEND": "ollama/mistral"}
    cfg = _load_with_env(env)
    # Defaults are applied
    assert cfg.db_path == "/data/contexta.db"
    assert cfg.export_path == "/exports"
    assert cfg.log_level == "WARNING"
    assert cfg.execution_mode == "UNIFIED"
    assert cfg.llm_api_key is None
    assert cfg.llm_base_url is None


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — specific valid and invalid configurations
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("backend", [
    "ollama/mistral",
    "openai/gpt-4o",
    "anthropic/claude-3-haiku",
    "azure/my-deployment",
    "cohere/command-r",
])
def test_known_valid_backends(backend: str) -> None:
    cfg = _load_with_env({"CONTEXTA_LLM_BACKEND": backend})
    assert cfg.llm_backend == backend


@pytest.mark.parametrize("backend", [
    "mistral",
    "gpt-4",
    "",
    "   ",
    "/no-provider",
    "no-model/",
])
def test_known_invalid_backends(backend: str) -> None:
    with pytest.raises(ConfigError):
        _load_with_env({"CONTEXTA_LLM_BACKEND": backend})


def test_execution_mode_default_is_unified() -> None:
    cfg = _load_with_env({"CONTEXTA_LLM_BACKEND": "ollama/mistral"})
    assert cfg.execution_mode == "UNIFIED"


def test_execution_mode_explicit_unified() -> None:
    cfg = _load_with_env({
        "CONTEXTA_LLM_BACKEND": "ollama/mistral",
        "CONTEXTA_EXECUTION_MODE": "unified",   # lowercase should normalise
    })
    assert cfg.execution_mode == "UNIFIED"


def test_execution_mode_invalid_raises() -> None:
    with pytest.raises(ConfigError):
        _load_with_env({
            "CONTEXTA_LLM_BACKEND": "ollama/mistral",
            "CONTEXTA_EXECUTION_MODE": "DISTRIBUTED",
        })


def test_log_level_normalisation() -> None:
    cfg = _load_with_env({
        "CONTEXTA_LLM_BACKEND": "ollama/mistral",
        "CONTEXTA_LOG_LEVEL": "debug",
    })
    assert cfg.log_level == "DEBUG"


def test_log_level_invalid_raises() -> None:
    with pytest.raises(ConfigError):
        _load_with_env({
            "CONTEXTA_LLM_BACKEND": "ollama/mistral",
            "CONTEXTA_LOG_LEVEL": "VERBOSE",
        })


def test_optional_fields_populated_from_env() -> None:
    cfg = _load_with_env({
        "CONTEXTA_LLM_BACKEND": "openai/gpt-4o",
        "CONTEXTA_LLM_API_KEY": "sk-test-key",
        "CONTEXTA_LLM_BASE_URL": "http://localhost:11434",
        "CONTEXTA_DB_PATH": "/tmp/test.db",
        "CONTEXTA_EXPORT_PATH": "/tmp/exports",
    })
    assert cfg.llm_api_key == "sk-test-key"
    assert cfg.llm_base_url == "http://localhost:11434"
    assert cfg.db_path == "/tmp/test.db"
    assert cfg.export_path == "/tmp/exports"


def test_config_error_message_is_human_readable() -> None:
    """ConfigError message must be a non-empty, descriptive string."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ConfigError) as exc_info:
            load_config()
    msg = str(exc_info.value)
    assert len(msg) > 10
    assert "Configuration error" in msg
