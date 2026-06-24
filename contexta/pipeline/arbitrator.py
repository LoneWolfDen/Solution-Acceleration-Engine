"""Layer 2 Synthesis — Arbitrator Engine.

The ``ArbitratorEngine`` takes all 12 completed ``ReviewNodePayload`` objects,
runs a single LLM call via the Arbitrator Persona, and returns an
``ArbitratorResult`` containing detected contradictions.

Design contracts
----------------
- ``run()`` raises ``ArbitratorError`` immediately if ``len(payloads) != 12``,
  before any LLM call is made (Property 13).
- Temperature-Zero Mode is enforced by ``call_llm()`` — the engine does not
  need to set temperature itself.
- JSON parsing failures raise ``ArbitratorError``, not bare ``JSONDecodeError``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

from ..llm.provider import LLMConfig, call_llm
from ..llm.prompts import PromptBuilder
from ..models.payloads import ReviewNodePayload


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
        Optional ``KnowledgeMemoryService``.  When provided, each detected
        contradiction is persisted to ``knowledge_observations`` via
        ``record_observation()`` so the system accumulates cross-session
        pattern memory.  When ``None`` the engine runs without persistence
        (backwards-compatible with all existing tests).
    """

    def __init__(
        self,
        config: LLMConfig,
        builder: PromptBuilder,
        knowledge_service: Optional["KnowledgeMemoryService"] = None,  # type: ignore[name-defined]
    ) -> None:
        self._config = config
        self._builder = builder
        self._knowledge_service = knowledge_service

    async def run(self, payloads: List[ReviewNodePayload]) -> ArbitratorResult:
        """Execute the Arbitrator synthesis.

        Parameters
        ----------
        payloads:
            Exactly 12 validated ``ReviewNodePayload`` objects — one per
            ``ReviewDimensionEnum`` value.

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

        serialised = [p.model_dump_json() for p in payloads]
        system, user = self._builder.build_arbitrator_prompt(serialised)

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

        # Persist each contradiction as a knowledge observation so the system
        # builds cross-session memory of recurring dimension friction patterns.
        if self._knowledge_service is not None and contradictions:
            for contradiction in contradictions:
                try:
                    await self._knowledge_service.record_observation(
                        source="arbitrator",
                        observation=contradiction.get("description", ""),
                        dimension_a=contradiction.get("dimension_a"),
                        dimension_b=contradiction.get("dimension_b"),
                    )
                except Exception as exc:  # noqa: BLE001
                    # Non-fatal: a DB error must never abort the arbitration result.
                    import logging
                    logging.getLogger(__name__).warning(
                        "ArbitratorEngine: failed to record observation: %s", exc
                    )

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

    The ``_normalise_json_content`` array-unwrapping fix in ``call_llm()``
    is applied automatically — no additional handling is needed here.

    Parameters
    ----------
    config:
        Application-level ``ContextaConfig`` — model identity and credentials
        are derived from it directly so callers do not need to construct a
        separate ``LLMConfig``.
    """

    def __init__(self, config: "ContextaConfig") -> None:  # type: ignore[name-defined]
        from ..config import ContextaConfig  # local import avoids top-level cycle
        from ..llm.provider import LLMConfig

        self._config = config
        self._llm_config = LLMConfig(
            model=config.llm_backend,
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
        )

    def _build_synthesis_prompt(
        self, findings: List
    ) -> "tuple[str, str]":
        """Delegate prompt construction to the centralised ``build_synthesis_prompt``
        helper in ``prompts.py``.

        Returns
        -------
        tuple[str, str]
            ``(system_prompt, user_prompt)`` ready for ``call_llm()``.

        Note
        ----
        The scaffold signature shows ``-> str`` but the correct return type is
        ``tuple[str, str]`` — ``call_llm()`` requires system and user separately.
        """
        from ..llm.prompts import build_synthesis_prompt

        return build_synthesis_prompt(findings)

    async def synthesize(self, findings: List) -> "ReconciliationReport":  # type: ignore[name-defined]
        """Execute the Layer 2 synthesis.

        Parameters
        ----------
        findings:
            ``IssueFinding`` objects collected from all completed Layer 1
            dimension payloads.  An empty list is accepted — the LLM will
            produce a minimal report reflecting no identified issues.

        Returns
        -------
        ReconciliationReport
            Validated synthesis output.

        Raises
        ------
        LayerTwoArbitratorError
            If the LLM call fails (network, non-200, or unexpected shape), or
            if the response cannot be validated against ``ReconciliationReport``.
        """
        from ..llm.models import ReconciliationReport
        from pydantic import ValidationError

        system, user = self._build_synthesis_prompt(findings)

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
