"""Shared pytest fixtures for the Sprint 2 test suite.

Fixtures defined here are available to all test modules without explicit
imports.  Each fixture is kept minimal — it creates only what the test
actually needs, nothing more.
"""

from __future__ import annotations

import asyncio

import pytest

from contexta.db.models import BlueprintRow
from contexta.llm.provider import LLMConfig
from contexta.mcp.artifact_registry import ArtifactRegistry


# ── Asyncio event loop compatibility ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_event_loop():
    """Ensure an asyncio event loop exists for sync tests that instantiate
    Textual widgets.

    Textual 8.x calls ``asyncio.get_event_loop()`` via ``asyncio.Lock.__init__``
    inside ``Widget.__init__``.  Python 3.9 raises ``RuntimeError`` when no
    event loop is set; Python 3.10+ auto-creates one.  The project requires
    Python ≥3.11, but this fixture allows the test suite to run in 3.9 sandbox
    environments without patching production code.

    **Async tests are unaffected**: pytest-asyncio (``asyncio_mode=auto``)
    creates and manages its own per-function event loop after this fixture
    yields.  The loop created here is only used by sync tests; it is closed
    during teardown only if we created it and it is not still running.
    """
    _created = None
    try:
        existing = asyncio.get_event_loop()
        if existing.is_closed():
            raise RuntimeError("existing loop is closed")
    except RuntimeError:
        _created = asyncio.new_event_loop()
        asyncio.set_event_loop(_created)
    try:
        yield
    finally:
        if _created is not None and not _created.is_running():
            _created.close()


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


@pytest.fixture()
def minimal_schema_json() -> str:
    """Minimal JSON schema string used to construct a PromptBuilder."""
    return '{"type": "object", "properties": {"dimension": {"type": "string"}}}'


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
