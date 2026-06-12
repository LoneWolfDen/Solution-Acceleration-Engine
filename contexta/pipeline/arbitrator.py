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
from typing import List

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
    """

    def __init__(self, config: LLMConfig, builder: PromptBuilder) -> None:
        self._config = config
        self._builder = builder

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

        return ArbitratorResult(
            contradictions=contradictions,
            raw_llm_response=response.content,
        )
