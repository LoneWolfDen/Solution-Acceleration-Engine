"""Shared mock factories for dimension-runner pipeline tests.

These helpers build deterministic LLM response stubs and AsyncMock objects
used across e2e, integration, and property tests.  Centralising them here
decouples the production module (contexta/pipeline/dimension_runner.py) from
any inline test data and ensures a single source of truth for the mock
contract.

Usage
-----
    from tests.fixtures import (
        make_dimension_llm_response,
        make_arbitrator_response,
        make_acompletion_sequential_mock,
    )
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from contexta.models.citations import SourceCitation
from contexta.models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from contexta.models.findings import IssueFinding
from contexta.models.payloads import ReviewNodePayload


# ── Dimension payload stubs ───────────────────────────────────────────────────


def make_dimension_llm_response(dim: ReviewDimensionEnum) -> str:
    """Return a valid ``ReviewNodePayload`` JSON string for *dim*.

    Produces a minimal but schema-valid payload: one AMBER finding with a
    single direct-reference citation, routed to the risk register.
    """
    payload = ReviewNodePayload(
        dimension=dim,
        findings=[
            IssueFinding(
                dimension=dim,
                confidence=ConfidenceEnum.AMBER,
                summary=f"Test finding for {dim.value}",
                detail=f"Detailed analysis of {dim.value}",
                citations=[
                    SourceCitation(
                        file_path="/proposal.md",
                        line_start=1,
                        line_end=5,
                        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
                        excerpt="test excerpt",
                    )
                ],
                mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
            )
        ],
        overall_confidence=ConfidenceEnum.AMBER,
        raw_llm_response="{}",
    )
    return payload.model_dump_json()


def make_arbitrator_response() -> str:
    """Return a minimal valid arbitrator JSON string with one contradiction."""
    return json.dumps(
        {
            "contradictions": [
                {
                    "dimension_a": "Risk",
                    "dimension_b": "Timeline",
                    "description": "Timeline is optimistic given identified risks",
                }
            ]
        }
    )


# ── AsyncMock factories ───────────────────────────────────────────────────────


def make_acompletion_mock_for_dim(dim: ReviewDimensionEnum) -> AsyncMock:
    """Return an ``AsyncMock`` that returns a valid dimension payload response."""
    choice = MagicMock()
    choice.message.content = make_dimension_llm_response(dim)
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    return AsyncMock(return_value=response)


def make_acompletion_sequential_mock() -> AsyncMock:
    """Return a mock that yields dimension responses then an arbitrator response.

    Call order:
    - Calls  1–12: each returns the matching ``ReviewNodePayload`` JSON for
      the corresponding ``ReviewDimensionEnum`` (ordered by enum declaration).
    - Call  13+:   returns the arbitrator contradiction JSON.

    This is the standard mock for full 12-dimension + arbitrator e2e flows.
    """
    call_count = 0
    dim_list = list(ReviewDimensionEnum)

    async def _side_effect(**kwargs):
        nonlocal call_count
        choice = MagicMock()
        if call_count < 12:
            dim = dim_list[call_count % 12]
            choice.message.content = make_dimension_llm_response(dim)
        else:
            choice.message.content = make_arbitrator_response()
        choice.finish_reason = "stop"
        response = MagicMock()
        response.choices = [choice]
        call_count += 1
        return response

    return AsyncMock(side_effect=_side_effect)
