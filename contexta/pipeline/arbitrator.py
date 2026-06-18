"""Layer 2 Synthesis — Arbitrator Engine.

The ``ArbitratorEngine`` takes all 12 completed ``ReviewNodePayload`` objects,
runs a single LLM call via the Arbitrator Persona, and returns an
``ArbitratorResult`` containing detected contradictions.

The ``LayerTwoArbitrator`` performs the full Layer 2 synthesis call, producing
a validated ``ReconciliationReport``.

Both engines optionally accept a ``KnowledgeContext`` so that prior user
interventions stored in KnowledgeMemory can be injected as Contextual
Constraints to guide contradiction detection and synthesis.

Design contracts
----------------
- ``ArbitratorEngine.run()`` raises ``ArbitratorError`` immediately if
  ``len(payloads) != 12``, before any LLM call is made (Property 13).
- Temperature-Zero Mode is enforced by ``call_llm()`` — the engines do not
  need to set temperature themselves.
- JSON parsing failures raise ``ArbitratorError``, not bare ``JSONDecodeError``.
- ``knowledge_service`` is optional in both engines; callers that have not
  wired KnowledgeMemory simply omit it and behaviour is unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from ..llm.provider import LLMConfig, call_llm
from ..llm.prompts import PromptBuilder
from ..models.payloads import ReviewNodePayload

if TYPE_CHECKING:
    from ..knowledge.memory import KnowledgeContext, KnowledgeMemoryService


# ── Exception ─────────────────────────────────────────────────────────────────


class ArbitratorError(Exception):
    """Raised when the Arbitrator call fails or its response cannot be parsed."""


# ── Result ────────────────────────────────────────────────────────────────────


@dataclass
class ArbitratorResult:
    """Structured output of the Layer 2 Arbitrator synthesis."""

    contradictions: List[dict]
    raw_llm_response: str


# ── Engine ────────────────────────────────────────────────────────────────────


class ArbitratorEngine:
    """Runs the Layer 2 synthesis LLM call.

    Parameters
    ----------
    config:
        LLM backend configuration passed through to ``call_llm()``.
    builder:
        ``PromptBuilder`` instance (uses the active blueprint).
    knowledge_service:
        Optional ``KnowledgeMemoryService``.  When provided, observations
        matching the supplied ``KnowledgeContext`` are fetched before the LLM
        call and injected as Contextual Constraints into the system prompt.
    """

    def __init__(
        self,
        config: LLMConfig,
        builder: PromptBuilder,
        knowledge_service: Optional["KnowledgeMemoryService"] = None,
    ) -> None:
        self._config = config
        self._builder = builder
        self._knowledge_service = knowledge_service

    async def run(
        self,
        payloads: List[ReviewNodePayload],
        context: Optional["KnowledgeContext"] = None,
    ) -> ArbitratorResult:
        """Execute the Arbitrator synthesis.

        Parameters
        ----------
        payloads:
            Exactly 12 validated ``ReviewNodePayload`` objects — one per
            ``ReviewDimensionEnum`` value.
        context:
            Optional ``KnowledgeContext`` used to fetch prior observations from
            KnowledgeMemory.  Ignored when ``knowledge_service`` is ``None``.

        Returns
        -------
        ArbitratorResult
            Contradictions list and the raw LLM response string.

        Raises
        ------
        ArbitratorError
            If ``len(payloads) != 12``, if the LLM call fails, or if the
            response JSON cannot be parsed.
        """
        if len(payloads) != 12:
            raise ArbitratorError(
                f"Arbitrator requires exactly 12 payloads, got {len(payloads)}"
            )

        observations = []
        if self._knowledge_service is not None and context is not None:
            observations = await self._knowledge_service.get_observations(context)

        serialised = [p.model_dump_json() for p in payloads]
        system, user = self._builder.build_arbitrator_prompt(serialised, observations)

        try:
            response = await call_llm(self._config, system, user)
        except Exception as exc:
            raise ArbitratorError(f"Arbitrator LLM call failed: {exc}") from exc

        try:
            data = json.loads(response.content)
            contradictions: List[dict] = data.get("contradictions", [])
        except (json.JSONDecodeError, AttributeError) as exc:
            raise ArbitratorError(
                f"Arbitrator response parsing failed: {exc}"
            ) from exc

        return ArbitratorResult(
            contradictions=contradictions,
            raw_llm_response=response.content,
        )



# ── Layer 2 Synthesis ─────────────────────────────────────────────────────────


class LayerTwoArbitratorError(Exception):
    """Raised when the Layer 2 synthesis LLM call fails or its response cannot
    be validated against ``ReconciliationReport``."""


class LayerTwoArbitrator:
    """Runs the Layer 2 synthesis pipeline.

    Accepts the aggregated ``IssueFinding`` objects from all 12 Layer 1
    dimensions, issues a single LLM synthesis call, and returns a validated
    ``ReconciliationReport``.

    When a ``KnowledgeMemoryService`` is provided, prior user interventions
    are fetched and injected as Contextual Constraints into the synthesis
    prompt so that the engine learns from accumulated manual corrections.

    The ``_normalise_json_content`` array-unwrapping fix in ``call_llm()``
    is applied automatically — no additional handling is needed here.

    Parameters
    ----------
    config:
        Application-level ``ContextaConfig`` — model identity and credentials
        are derived from it directly so callers do not need to construct a
        separate ``LLMConfig``.
    knowledge_service:
        Optional ``KnowledgeMemoryService``.  When provided, observations are
        fetched before synthesis and injected into the system prompt.
    """

    def __init__(
        self,
        config: "ContextaConfig",  # type: ignore[name-defined]
        knowledge_service: Optional["KnowledgeMemoryService"] = None,
    ) -> None:
        from ..config import ContextaConfig  # local import avoids top-level cycle
        from ..llm.provider import LLMConfig

        self._config = config
        self._llm_config = LLMConfig(
            model=config.llm_backend,
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
        )
        self._knowledge_service = knowledge_service

    def _build_synthesis_prompt(
        self,
        findings: List,
        observations: Optional[list] = None,
    ) -> "tuple[str, str]":
        """Delegate prompt construction to ``build_synthesis_prompt``.

        Passes *observations* through so that Contextual Constraints are
        injected when KnowledgeMemory has prior interventions available.

        Returns
        -------
        tuple[str, str]
            ``(system_prompt, user_prompt)`` ready for ``call_llm()``.
        """
        from ..llm.prompts import build_synthesis_prompt

        return build_synthesis_prompt(findings, observations or [])

    async def synthesize(
        self,
        findings: List,
        context: Optional["KnowledgeContext"] = None,
    ) -> "ReconciliationReport":  # type: ignore[name-defined]
        """Execute the Layer 2 synthesis.

        Parameters
        ----------
        findings:
            ``IssueFinding`` objects collected from all completed Layer 1
            dimension payloads.  An empty list is accepted — the LLM will
            produce a minimal report reflecting no identified issues.
        context:
            Optional ``KnowledgeContext`` used to fetch prior observations.
            Ignored when ``knowledge_service`` is ``None``.

        Returns
        -------
        ReconciliationReport
            Validated synthesis output.

        Raises
        ------
        LayerTwoArbitratorError
            If the LLM call fails or the response cannot be validated.
        """
        from ..llm.models import ReconciliationReport
        from pydantic import ValidationError

        observations = []
        if self._knowledge_service is not None and context is not None:
            observations = await self._knowledge_service.get_observations(context)

        system, user = self._build_synthesis_prompt(findings, observations)

        try:
            response = await call_llm(self._llm_config, system, user)
        except Exception as exc:
            raise LayerTwoArbitratorError(
                f"Layer 2 synthesis LLM call failed: {exc}"
            ) from exc

        try:
            report = ReconciliationReport.model_validate_json(response.content)
        except (ValidationError, ValueError) as exc:
            raise LayerTwoArbitratorError(
                f"Layer 2 synthesis response validation failed: {exc}"
            ) from exc

        return report
