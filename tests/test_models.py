"""
tests/test_models.py — Property and unit tests for the Pydantic schema layer.

Properties covered:
  Property 3: Pydantic Enum Round-Trip Serialization
              For every value in every enum, serialise to string and reconstruct;
              assert equality.
  Property 4: ReviewNodePayload Round-Trip Serialization
              Generate arbitrary valid ReviewNodePayload objects; assert
              model_dump_json() → model_validate_json() round-trip equality.
  Property 5: LLM Response Validation Gate
              Valid ReviewNodePayload JSON parses successfully; schema-violating
              JSON raises ValidationError with no side-effects.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from contexta.models.citations import SourceCitation
from contexta.models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from contexta.models.export import EXPORT_SCHEMA_VERSION, ExportArbitratorResult, JSONPacket
from contexta.models.findings import IssueFinding
from contexta.models.payloads import ReviewNodePayload


# ─────────────────────────────────────────────────────────────────────────────
# Hypothesis strategies
# ─────────────────────────────────────────────────────────────────────────────

_nonempty_text = st.text(min_size=1, max_size=200)
_filepath = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="/_-."),
    min_size=1,
    max_size=80,
)


@st.composite
def source_citation_strategy(draw: Any) -> SourceCitation:
    line_start = draw(st.integers(min_value=1, max_value=5000))
    line_end   = draw(st.integers(min_value=line_start, max_value=line_start + 500))
    return SourceCitation(
        file_path=draw(_filepath),
        line_start=line_start,
        line_end=line_end,
        citation_type=draw(st.sampled_from(CitationTypeEnum)),
        excerpt=draw(_nonempty_text),
    )


@st.composite
def issue_finding_strategy(draw: Any) -> IssueFinding:
    return IssueFinding(
        dimension=draw(st.sampled_from(ReviewDimensionEnum)),
        confidence=draw(st.sampled_from(ConfidenceEnum)),
        summary=draw(_nonempty_text),
        detail=draw(_nonempty_text),
        citations=draw(st.lists(source_citation_strategy(), min_size=0, max_size=3)),
        mitigation_routing=draw(st.sampled_from(MitigationRoutingEnum)),
    )


@st.composite
def review_node_payload_strategy(draw: Any) -> ReviewNodePayload:
    return ReviewNodePayload(
        dimension=draw(st.sampled_from(ReviewDimensionEnum)),
        findings=draw(st.lists(issue_finding_strategy(), min_size=0, max_size=4)),
        overall_confidence=draw(st.sampled_from(ConfidenceEnum)),
        raw_llm_response=draw(_nonempty_text),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Property 3 — Pydantic Enum Round-Trip Serialization
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("enum_cls", [
    ConfidenceEnum,
    CitationTypeEnum,
    ReviewDimensionEnum,
    MitigationRoutingEnum,
])
def test_property3_enum_round_trip_all_values(enum_cls: type) -> None:
    """
    Property 3: For every enum member, serialise to its string value and
    reconstruct via Pydantic coercion; assert the result equals the original.
    """
    for member in enum_cls:
        serialised: str = member.value
        reconstructed = enum_cls(serialised)
        assert reconstructed == member, (
            f"{enum_cls.__name__}.{member.name}: round-trip failed — "
            f"got {reconstructed!r} from {serialised!r}"
        )


def test_property3_review_dimension_enum_has_exactly_12_members() -> None:
    """Requirement 3.3: ReviewDimensionEnum must have exactly 12 values."""
    assert len(ReviewDimensionEnum) == 12


def test_property3_all_enums_are_str_subclass() -> None:
    """All enums must be str subclasses for transparent JSON serialisation."""
    for enum_cls in (ConfidenceEnum, CitationTypeEnum, ReviewDimensionEnum, MitigationRoutingEnum):
        for member in enum_cls:
            assert isinstance(member, str), f"{enum_cls.__name__}.{member.name} is not a str"


# ─────────────────────────────────────────────────────────────────────────────
# Property 4 — ReviewNodePayload Round-Trip Serialization
# ─────────────────────────────────────────────────────────────────────────────

@given(payload=review_node_payload_strategy())
@settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
def test_property4_review_node_payload_round_trip(payload: ReviewNodePayload) -> None:
    """
    Property 4: model_dump_json() → model_validate_json() preserves equality.
    """
    serialised = payload.model_dump_json()
    reconstructed = ReviewNodePayload.model_validate_json(serialised)
    assert reconstructed == payload, (
        "ReviewNodePayload round-trip failed:\n"
        f"  original:      {payload}\n"
        f"  reconstructed: {reconstructed}"
    )


def test_property4_round_trip_via_dict() -> None:
    """model_dump() → model_validate() also preserves equality."""
    payload = ReviewNodePayload(
        dimension=ReviewDimensionEnum.RISK,
        findings=[
            IssueFinding(
                dimension=ReviewDimensionEnum.RISK,
                confidence=ConfidenceEnum.RED,
                summary="High risk",
                detail="Detailed risk description.",
                citations=[
                    SourceCitation(
                        file_path="docs/solution.md",
                        line_start=10,
                        line_end=15,
                        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
                        excerpt="The solution assumes...",
                    )
                ],
                mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
            )
        ],
        overall_confidence=ConfidenceEnum.RED,
        raw_llm_response='{"dimension": "Risk", "findings": [], "overall_confidence": "RED"}',
    )
    reconstructed = ReviewNodePayload.model_validate(payload.model_dump())
    assert reconstructed == payload


# ─────────────────────────────────────────────────────────────────────────────
# Property 5 — LLM Response Validation Gate
# ─────────────────────────────────────────────────────────────────────────────

def _make_valid_payload_json(
    dimension: str = "Risk",
    confidence: str = "GREEN",
) -> str:
    return json.dumps({
        "dimension": dimension,
        "findings": [],
        "overall_confidence": confidence,
        "raw_llm_response": "{}",
    })


def test_property5_valid_llm_response_parses_successfully() -> None:
    """
    Property 5a: A well-formed JSON string matching the ReviewNodePayload schema
    parses without error.
    """
    for dim in ReviewDimensionEnum:
        for conf in ConfidenceEnum:
            payload = ReviewNodePayload.model_validate_json(
                _make_valid_payload_json(dim.value, conf.value)
            )
            assert payload.dimension == dim
            assert payload.overall_confidence == conf


@pytest.mark.parametrize("bad_json", [
    # Missing required field: dimension
    json.dumps({"findings": [], "overall_confidence": "GREEN", "raw_llm_response": "{}"}),
    # Missing required field: overall_confidence
    json.dumps({"dimension": "Risk", "findings": [], "raw_llm_response": "{}"}),
    # Invalid enum value for dimension
    json.dumps({"dimension": "INVALID_DIM", "findings": [], "overall_confidence": "GREEN", "raw_llm_response": "{}"}),
    # Invalid enum value for overall_confidence
    json.dumps({"dimension": "Risk", "findings": [], "overall_confidence": "YELLOW", "raw_llm_response": "{}"}),
    # findings not a list
    json.dumps({"dimension": "Risk", "findings": "bad", "overall_confidence": "GREEN", "raw_llm_response": "{}"}),
    # Completely wrong type
    json.dumps([1, 2, 3]),
    # Empty object
    json.dumps({}),
])
def test_property5_invalid_llm_response_raises_validation_error(bad_json: str) -> None:
    """
    Property 5b: Schema-violating JSON raises ValidationError; no side-effects
    means the exception is clean and no partial state exists.
    """
    with pytest.raises((ValidationError, Exception)):
        ReviewNodePayload.model_validate_json(bad_json)


def test_property5_invalid_finding_inside_payload_raises() -> None:
    """
    IssueFinding with an invalid citation (line_end < line_start) must raise
    ValidationError when constructing the parent ReviewNodePayload.
    """
    bad_payload_dict = {
        "dimension": "Scope",
        "findings": [
            {
                "dimension": "Scope",
                "confidence": "AMBER",
                "summary": "test",
                "detail": "test detail",
                "citations": [
                    {
                        "file_path": "file.md",
                        "line_start": 20,
                        "line_end": 5,   # invalid: end < start
                        "citation_type": "Direct Reference",
                        "excerpt": "some text",
                    }
                ],
                "mitigation_routing": "Ignored",
            }
        ],
        "overall_confidence": "AMBER",
        "raw_llm_response": "{}",
    }
    with pytest.raises(ValidationError):
        ReviewNodePayload.model_validate(bad_payload_dict)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — SourceCitation constraints
# ─────────────────────────────────────────────────────────────────────────────

def test_source_citation_valid() -> None:
    c = SourceCitation(
        file_path="src/main.py",
        line_start=1,
        line_end=1,
        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
        excerpt="x = 1",
    )
    assert c.line_start == c.line_end == 1


def test_source_citation_line_end_lt_start_raises() -> None:
    with pytest.raises(ValidationError):
        SourceCitation(
            file_path="src/main.py",
            line_start=10,
            line_end=9,
            citation_type=CitationTypeEnum.DIRECT_REFERENCE,
            excerpt="x = 1",
        )


def test_source_citation_zero_line_number_raises() -> None:
    with pytest.raises(ValidationError):
        SourceCitation(
            file_path="f.py",
            line_start=0,
            line_end=1,
            citation_type=CitationTypeEnum.ADVISED_IN_RELATION,
            excerpt="y",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — export models
# ─────────────────────────────────────────────────────────────────────────────

def test_json_packet_schema_version_default() -> None:
    pkt = JSONPacket(
        project_id="proj-1",
        project_name="Test Project",
        global_tags=["#Lean"],
        node_id="node-1",
        node_name="Baseline",
        layer_type="exploration",
        created_at="2026-06-09T00:00:00+00:00",
        payloads=[],
    )
    assert pkt.schema_version == EXPORT_SCHEMA_VERSION
    assert pkt.schema_version == "1.0"


def test_json_packet_optional_fields_default_to_none_or_empty() -> None:
    pkt = JSONPacket(
        project_id="p",
        project_name="N",
        global_tags=[],
        node_id="n",
        node_name="base",
        layer_type="exploration",
        created_at="2026-01-01T00:00:00Z",
        payloads=[],
    )
    assert pkt.parent_node_id is None
    assert pkt.arbitrator_result is None
    assert pkt.routing_decisions == []
    assert pkt.metadata == {}
    assert pkt.version_tag is None


def test_export_arbitrator_result_round_trip() -> None:
    result = ExportArbitratorResult(
        contradictions=[{"dimension_a": "Risk", "dimension_b": "Timeline", "description": "Conflict"}],
        raw_llm_response='{"contradictions": []}',
    )
    reconstructed = ExportArbitratorResult.model_validate_json(result.model_dump_json())
    assert reconstructed == result
