"""Shared pytest fixtures for the Sprint 2 test suite.

Fixtures defined here are available to all test modules without explicit
imports.  Each fixture is kept minimal — it creates only what the test
actually needs, nothing more.
"""

from __future__ import annotations

import pytest

from contexta.db.models import BlueprintRow
from contexta.llm.provider import LLMConfig
from contexta.mcp.artifact_registry import ArtifactRegistry


# ── LLM fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def llm_config() -> LLMConfig:
    """Minimal ``LLMConfig`` for a local Ollama backend.

    No real network calls are made in tests — ``litellm.acompletion`` is
    always mocked.
    """
    return LLMConfig(model="ollama/mistral")


@pytest.fixture()
def llm_config_with_key() -> LLMConfig:
    """``LLMConfig`` with an API key and custom base URL."""
    return LLMConfig(
        model="openai/gpt-4o",
        api_key="sk-test-key",
        base_url="https://api.example.com/v1",
    )


# ── Blueprint fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def blueprint_row() -> BlueprintRow:
    """Active blueprint with a non-trivial master_prompt_text."""
    return BlueprintRow(
        id="bp-001",
        blueprint_name="Default Review Blueprint",
        version_string="1.0.0",
        master_prompt_text=(
            "Review the provided solution proposal with rigorous scrutiny. "
            "Focus on delivery risk and technical feasibility."
        ),
        is_active=True,
    )


# ── Registry fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def registry() -> ArtifactRegistry:
    """Fresh, empty ``ArtifactRegistry``."""
    return ArtifactRegistry()



# ── Layer 2 config fixture ────────────────────────────────────────────────────


@pytest.fixture()
def mock_config() -> "ContextaConfig":
    """Minimal ``ContextaConfig`` for Layer 2 Arbitrator unit tests.

    Passes ``llm_backend`` directly so no environment variable is required.
    No real LLM calls are made — ``litellm.acompletion`` is always mocked.
    """
    from contexta.config import ContextaConfig

    return ContextaConfig(llm_backend="ollama/mistral")
