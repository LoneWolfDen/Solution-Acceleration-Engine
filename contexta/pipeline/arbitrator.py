"""Pipeline — Layer 2 synthesis (ArbitratorEngine).

Design contracts
----------------
- ``ArbitratorEngine.run()`` raises ``ArbitratorError`` **immediately** if
  ``len(payloads) != 12`` — before any LLM call is made.  This satisfies
  Property 13 (Arbitrator Receives All 12 Payloads).
- The LLM call goes through ``call_llm()`` which unconditionally applies
  ``temperature=0.0`` and ``response_format={"type": "json_object"}``.
- The raw JSON response is parsed with ``json.loads()``.  Any
  ``json.JSONDecodeError`` or missing ``"contradictions"`` key is wrapped
  in ``ArbitratorError`` — callers never receive an unstructured exception.
- ``ArbitratorResult`` is a plain dataclass; downstream code must not rely
  on Pydantic validation for this object (it is not a DB-persisted model).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List

from ..llm.provider import LLMConfig, LLMCallError, call_llm
from ..llm.prompts import PromptBuilder
from ..models.payloads import ReviewNodePayload

# Required number of dimension payloads — mirrors ReviewDimensionEnum cardinality.
_REQUIRED_PAYLOAD_COUNT: int = 12


# ── Exceptions ─────────────────────────────────────────────────────────────────


class ArbitratorError(Exception):
    """Raised when the Arbitrator cannot complete synthesis.

    Causes include:
    - Incorrect number of input payloads (must be exactly 12).
    - LLM call failure propagated from ``call_llm()``.
    - JSON parsing failure on the LLM response.
    - Missing ``"contradictions"`` key in the parsed response.
    """


# ── Result model ──────────────────────────────────────────────────────────────


@dataclass
class ArbitratorResult:
    """Structured output of a Layer 2 synthesis run.

    Attributes
    ----------
    contradictions:
        List of contradiction dicts, each containing keys:
        ``"dimension_a"``, ``"dimension_b"``, ``"description"``.
    raw_llm_response:
        The verbatim string returned by the LLM before parsing, preserved
        for audit and debugging.
    """

    contradictions: List[Dict] = field(default_factory=list)
    raw_llm_response: str = ""


# ── Engine ────────────────────────────────────────────────────────────────────


class ArbitratorEngine:
    """Layer 2 synthesis engine — contradiction detection across 12 dimensions.

    Parameters
    ----------
    config:
        LiteLLM configuration (model, optional api_key / base_url).
    builder:
        ``PromptBuilder`` pre-loaded with the active blueprint.
        ``build_arbitrator_prompt()`` is called to assemble the system and
        user messages.
    """

    def __init__(self, config: LLMConfig, builder: PromptBuilder) -> None:
        self._config = config
        self._builder = builder

    async def run(self, payloads: List[ReviewNodePayload]) -> ArbitratorResult:
        """Execute Layer 2 synthesis over 12 validated dimension payloads.

        Parameters
        ----------
        payloads:
            Exactly 12 ``ReviewNodePayload`` objects — one per
            ``ReviewDimensionEnum`` value.  Supplying any other count raises
            ``ArbitratorError`` without making an LLM call.

        Returns
        -------
        ArbitratorResult
            Parsed contradiction list and raw LLM response string.

        Raises
        ------
        ArbitratorError
            - If ``len(payloads) != 12`` (guard fires before LLM call).
            - If the LLM call fails (wraps ``LLMCallError``).
            - If the response is not valid JSON.
            - If the parsed JSON lacks the ``"contradictions"`` key.
        """
        if len(payloads) != _REQUIRED_PAYLOAD_COUNT:
            raise ArbitratorError(
                f"Arbitrator requires exactly {_REQUIRED_PAYLOAD_COUNT} payloads, "
                f"got {len(payloads)}"
            )

        serialised = [p.model_dump_json() for p in payloads]
        system, user = self._builder.build_arbitrator_prompt(serialised)

        try:
            llm_response = await call_llm(self._config, system, user)
        except LLMCallError as exc:
            raise ArbitratorError(
                f"Arbitrator LLM call failed: {exc}"
            ) from exc

        try:
            data = json.loads(llm_response.content)
        except json.JSONDecodeError as exc:
            raise ArbitratorError(
                f"Arbitrator response is not valid JSON: {exc}"
            ) from exc

        if "contradictions" not in data:
            raise ArbitratorError(
                "Arbitrator response JSON is missing required key 'contradictions'"
            )

        return ArbitratorResult(
            contradictions=data["contradictions"],
            raw_llm_response=llm_response.content,
        )
