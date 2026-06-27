"""tests/test_arbitrator_pipeline.py — Formal test suite for the arbitration pipeline.

Formalises the validation logic that was originally in the root-level
``debug_arbitrator.py`` harness script.  Tests run without a live LLM or
database — all I/O is mocked at the boundary.

Coverage targets
----------------
- ``ContextaConfig.as_llm_config()``     — attribute mapping correctness
- ``estimate_token_count()``             — heuristic token estimation
- ``ArbitrationService.run()``           — happy path, full status sequence
- ``TokenLimitError``                    — pre-flight guard fires before LLM call
- ``ArbitratorError`` propagation        — engine errors surface as FAILED status
- Rate-limit signal detection            — "rate"/"429"/"tpm" → RATE_LIMITED status
- Missing blueprint guard                — None blueprint → RuntimeError + FAILED
- ``as_llm_config()`` optional fields   — None values when env vars unset
"""

from __future__ import annotations

import json
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contexta.db.models import BlueprintRow
from contexta.llm.provider import LLMConfig
from contexta.models.citations import SourceCitation
from contexta.models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from contexta.models.findings import IssueFinding
from contexta.models.payloads import ReviewNodePayload
from contexta.pipeline.arbitrator import ArbitratorError
from contexta.services.arbitration import (
    GROQ_TPM_LIMIT,
    ArbitrationService,
    ArbitrationStatus,
    TokenLimitError,
    estimate_token_count,
)


# ─────────────────────────────────────────────────────────────────────────────
# Shared test fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_finding(dim: ReviewDimensionEnum) -> IssueFinding:
    return IssueFinding(
        dimension=dim,
        confidence=ConfidenceEnum.GREEN,
        summary="No issues detected.",
        detail="Full analysis shows no critical gaps.",
        citations=[
            SourceCitation(
                file_path="docs/sow.pdf",
                line_start=1,
                line_end=1,
                citation_type=CitationTypeEnum.DIRECT_REFERENCE,
                excerpt="Sample text.",
            )
        ],
        mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
    )


def _make_payload(dim: ReviewDimensionEnum) -> ReviewNodePayload:
    return ReviewNodePayload(
        dimension=dim,
        findings=[_make_finding(dim)],
        overall_confidence=ConfidenceEnum.GREEN,
        raw_llm_response="minimal",
    )


def _make_twelve_payloads() -> List[ReviewNodePayload]:
    """Return exactly 12 payloads — one per ``ReviewDimensionEnum`` value."""
    return [_make_payload(dim) for dim in ReviewDimensionEnum]


def _make_blueprint() -> BlueprintRow:
    return BlueprintRow(
        id="bp-test-001",
        blueprint_name="Test Blueprint",
        version_string="1.0.0",
        master_prompt_text=(
            "You are a senior technical delivery manager. "
            "Review the proposal with rigorous scrutiny."
        ),
        is_active=True,
    )


def _make_acompletion_mock(contradictions: list | None = None) -> AsyncMock:
    """Return an AsyncMock for ``litellm.acompletion`` with a valid JSON response."""
    if contradictions is None:
        contradictions = [
            {
                "dimension_a": "Risk",
                "dimension_b": "Timeline",
                "description": "Timeline is optimistic given identified risks.",
            }
        ]
    choice = MagicMock()
    choice.message.content = json.dumps({"contradictions": contradictions})
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    return AsyncMock(return_value=response)


# ─────────────────────────────────────────────────────────────────────────────
# ContextaConfig.as_llm_config() — attribute mapping
# ─────────────────────────────────────────────────────────────────────────────


class TestAsLLMConfig:

    def test_maps_all_three_fields(self, monkeypatch):
        """as_llm_config() produces an LLMConfig with all three attributes mapped."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test_key_abc")
        monkeypatch.setenv("CONTEXTA_LLM_BASE_URL", "https://api.groq.com/openai/v1")

        from contexta.config import ContextaConfig

        cfg = ContextaConfig()
        llm = cfg.as_llm_config()

        assert isinstance(llm, LLMConfig)
        assert llm.model == "groq/llama3-8b-8192"
        assert llm.api_key == "gsk_test_key_abc"
        assert llm.base_url == "https://api.groq.com/openai/v1"

    def test_optional_fields_are_none_when_unset(self, monkeypatch):
        """api_key and base_url are None when the corresponding env vars are absent."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "ollama/mistral")
        monkeypatch.delenv("CONTEXTA_LLM_API_KEY", raising=False)
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        cfg = ContextaConfig()
        llm = cfg.as_llm_config()

        assert llm.model == "ollama/mistral"
        assert llm.api_key is None
        assert llm.base_url is None

    def test_model_matches_llm_backend_verbatim(self, monkeypatch):
        """LLMConfig.model is exactly llm_backend — no transformation applied."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "openai/gpt-4o")
        monkeypatch.delenv("CONTEXTA_LLM_API_KEY", raising=False)
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        cfg = ContextaConfig()
        assert cfg.as_llm_config().model == cfg.llm_backend


# ─────────────────────────────────────────────────────────────────────────────
# estimate_token_count() — heuristic
# ─────────────────────────────────────────────────────────────────────────────


class TestEstimateTokenCount:

    def test_returns_int(self):
        assert isinstance(estimate_token_count(["hello world"]), int)

    def test_empty_list_returns_zero(self):
        assert estimate_token_count([]) == 0

    def test_empty_strings_return_zero(self):
        assert estimate_token_count(["", ""]) == 0

    def test_longer_text_produces_higher_estimate(self):
        short = estimate_token_count(["hi"])
        long = estimate_token_count(["hi " * 500])
        assert long > short

    def test_multiple_strings_are_summed(self):
        combined = estimate_token_count(["aaaa", "aaaa"])  # 8 chars → 2 tokens
        single = estimate_token_count(["aaaaaaaa"])         # 8 chars → 2 tokens
        assert combined == single

    def test_groq_tpm_limit_constant_is_twelve_thousand(self):
        """Sanity-check: the exported constant matches the expected ceiling."""
        assert GROQ_TPM_LIMIT == 12_000


# ─────────────────────────────────────────────────────────────────────────────
# ArbitrationService.run() — happy path
# ─────────────────────────────────────────────────────────────────────────────


class TestArbitrationServiceSuccess:

    @pytest.mark.asyncio
    async def test_returns_arbitrator_result(self, monkeypatch):
        """run() returns an ArbitratorResult with parsed contradictions."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test")
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        config = ContextaConfig()
        conn = AsyncMock()

        with (
            patch(
                "contexta.services.arbitration.get_active_blueprint",
                AsyncMock(return_value=_make_blueprint()),
            ),
            patch(
                "contexta.llm.provider.litellm.acompletion",
                _make_acompletion_mock(),
            ),
        ):
            service = ArbitrationService(config, conn)
            result = await service.run(_make_twelve_payloads())

        assert len(result.contradictions) == 1
        assert result.contradictions[0]["dimension_a"] == "Risk"
        assert result.contradictions[0]["dimension_b"] == "Timeline"

    @pytest.mark.asyncio
    async def test_emits_processing_then_complete(self, monkeypatch):
        """Status callbacks fire in order: PROCESSING → COMPLETE."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test")
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        config = ContextaConfig()
        conn = AsyncMock()
        statuses: list[tuple[ArbitrationStatus, str | None]] = []

        async def capture(status, detail):
            statuses.append((status, detail))

        with (
            patch(
                "contexta.services.arbitration.get_active_blueprint",
                AsyncMock(return_value=_make_blueprint()),
            ),
            patch(
                "contexta.llm.provider.litellm.acompletion",
                _make_acompletion_mock(contradictions=[]),
            ),
        ):
            service = ArbitrationService(config, conn, on_status_change=capture)
            await service.run(_make_twelve_payloads())

        assert statuses[0] == (ArbitrationStatus.PROCESSING, None)
        assert statuses[-1] == (ArbitrationStatus.COMPLETE, None)

    @pytest.mark.asyncio
    async def test_no_contradictions_returns_empty_list(self, monkeypatch):
        """run() with a clean LLM response returns an empty contradictions list."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test")
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        config = ContextaConfig()
        conn = AsyncMock()

        with (
            patch(
                "contexta.services.arbitration.get_active_blueprint",
                AsyncMock(return_value=_make_blueprint()),
            ),
            patch(
                "contexta.llm.provider.litellm.acompletion",
                _make_acompletion_mock(contradictions=[]),
            ),
        ):
            service = ArbitrationService(config, conn)
            result = await service.run(_make_twelve_payloads())

        assert result.contradictions == []


# ─────────────────────────────────────────────────────────────────────────────
# TokenLimitError — pre-flight guard
# ─────────────────────────────────────────────────────────────────────────────


class TestTokenLimitGuard:

    @pytest.mark.asyncio
    async def test_raises_token_limit_error_when_exceeded(self, monkeypatch):
        """TokenLimitError is raised when estimated tokens exceed tpm_limit=1."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test")
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        config = ContextaConfig()
        conn = AsyncMock()

        with patch(
            "contexta.services.arbitration.get_active_blueprint",
            AsyncMock(return_value=_make_blueprint()),
        ):
            service = ArbitrationService(config, conn, tpm_limit=1)
            with pytest.raises(TokenLimitError, match="TPM limit"):
                await service.run(_make_twelve_payloads())

    @pytest.mark.asyncio
    async def test_rate_limited_status_emitted_before_raise(self, monkeypatch):
        """RATE_LIMITED status is fired before TokenLimitError propagates."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test")
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        config = ContextaConfig()
        conn = AsyncMock()
        statuses: list[ArbitrationStatus] = []

        async def capture(status, detail):
            statuses.append(status)

        with patch(
            "contexta.services.arbitration.get_active_blueprint",
            AsyncMock(return_value=_make_blueprint()),
        ):
            service = ArbitrationService(config, conn, on_status_change=capture, tpm_limit=1)
            with pytest.raises(TokenLimitError):
                await service.run(_make_twelve_payloads())

        assert ArbitrationStatus.RATE_LIMITED in statuses

    @pytest.mark.asyncio
    async def test_llm_not_called_when_token_limit_exceeded(self, monkeypatch):
        """No LLM call is made when the pre-flight token check fails."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test")
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        config = ContextaConfig()
        conn = AsyncMock()
        mock_llm = _make_acompletion_mock()

        with (
            patch(
                "contexta.services.arbitration.get_active_blueprint",
                AsyncMock(return_value=_make_blueprint()),
            ),
            patch("contexta.llm.provider.litellm.acompletion", mock_llm),
        ):
            service = ArbitrationService(config, conn, tpm_limit=1)
            with pytest.raises(TokenLimitError):
                await service.run(_make_twelve_payloads())

        mock_llm.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Error propagation — ArbitratorError → FAILED / RATE_LIMITED
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorPropagation:

    @pytest.mark.asyncio
    async def test_arbitrator_error_propagates_and_emits_failed(self, monkeypatch):
        """ArbitratorError from the engine emits FAILED status and is re-raised."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test")
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        config = ContextaConfig()
        conn = AsyncMock()
        statuses: list[ArbitrationStatus] = []

        async def capture(status, detail):
            statuses.append(status)

        failing_llm = AsyncMock(side_effect=RuntimeError("network timeout"))

        with (
            patch(
                "contexta.services.arbitration.get_active_blueprint",
                AsyncMock(return_value=_make_blueprint()),
            ),
            patch("contexta.llm.provider.litellm.acompletion", failing_llm),
        ):
            service = ArbitrationService(config, conn, on_status_change=capture)
            with pytest.raises(ArbitratorError, match="network timeout"):
                await service.run(_make_twelve_payloads())

        assert ArbitrationStatus.FAILED in statuses
        assert ArbitrationStatus.COMPLETE not in statuses

    @pytest.mark.asyncio
    async def test_rate_limit_signal_in_error_emits_rate_limited(self, monkeypatch):
        """An error message containing 'rate' routes to RATE_LIMITED, not FAILED."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test")
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        config = ContextaConfig()
        conn = AsyncMock()
        statuses: list[ArbitrationStatus] = []

        async def capture(status, detail):
            statuses.append(status)

        rate_limit_llm = AsyncMock(
            side_effect=RuntimeError("429 rate limit exceeded for model")
        )

        with (
            patch(
                "contexta.services.arbitration.get_active_blueprint",
                AsyncMock(return_value=_make_blueprint()),
            ),
            patch("contexta.llm.provider.litellm.acompletion", rate_limit_llm),
        ):
            service = ArbitrationService(config, conn, on_status_change=capture)
            with pytest.raises(ArbitratorError):
                await service.run(_make_twelve_payloads())

        assert ArbitrationStatus.RATE_LIMITED in statuses
        assert ArbitrationStatus.FAILED not in statuses

    @pytest.mark.asyncio
    async def test_tpm_keyword_in_error_emits_rate_limited(self, monkeypatch):
        """Error message containing 'tpm' also routes to RATE_LIMITED."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test")
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        config = ContextaConfig()
        conn = AsyncMock()
        statuses: list[ArbitrationStatus] = []

        async def capture(status, detail):
            statuses.append(status)

        tpm_error_llm = AsyncMock(side_effect=RuntimeError("TPM quota exhausted"))

        with (
            patch(
                "contexta.services.arbitration.get_active_blueprint",
                AsyncMock(return_value=_make_blueprint()),
            ),
            patch("contexta.llm.provider.litellm.acompletion", tpm_error_llm),
        ):
            service = ArbitrationService(config, conn, on_status_change=capture)
            with pytest.raises(ArbitratorError):
                await service.run(_make_twelve_payloads())

        assert ArbitrationStatus.RATE_LIMITED in statuses

    @pytest.mark.asyncio
    async def test_missing_blueprint_raises_runtime_error_with_failed_status(
        self, monkeypatch
    ):
        """None blueprint from DB raises RuntimeError and emits FAILED status."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test")
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        config = ContextaConfig()
        conn = AsyncMock()
        statuses: list[ArbitrationStatus] = []

        async def capture(status, detail):
            statuses.append(status)

        with patch(
            "contexta.services.arbitration.get_active_blueprint",
            AsyncMock(return_value=None),
        ):
            service = ArbitrationService(config, conn, on_status_change=capture)
            with pytest.raises(RuntimeError, match="No active blueprint"):
                await service.run(_make_twelve_payloads())

        assert ArbitrationStatus.FAILED in statuses
        assert ArbitrationStatus.COMPLETE not in statuses

    @pytest.mark.asyncio
    async def test_processing_status_always_fires_first(self, monkeypatch):
        """PROCESSING is always the first status emitted, even when an error follows."""
        monkeypatch.setenv("CONTEXTA_LLM_BACKEND", "groq/llama3-8b-8192")
        monkeypatch.setenv("CONTEXTA_LLM_API_KEY", "gsk_test")
        monkeypatch.delenv("CONTEXTA_LLM_BASE_URL", raising=False)

        from contexta.config import ContextaConfig

        config = ContextaConfig()
        conn = AsyncMock()
        statuses: list[ArbitrationStatus] = []

        async def capture(status, detail):
            statuses.append(status)

        with patch(
            "contexta.services.arbitration.get_active_blueprint",
            AsyncMock(return_value=None),
        ):
            service = ArbitrationService(config, conn, on_status_change=capture)
            with pytest.raises(RuntimeError):
                await service.run(_make_twelve_payloads())

        assert statuses[0] == ArbitrationStatus.PROCESSING
