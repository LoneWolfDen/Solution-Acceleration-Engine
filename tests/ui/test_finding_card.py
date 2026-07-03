"""Milestone 6.4 — tests/ui/test_finding_card.py

Tests for FindingCard component data contracts.

The FindingCard renders: type badge, severity badge, text body, source_artifact.
Tests validate:
  - All required fields present on FindingItem
  - Type badge shows the correct label for each ReviewDimensionEnum value
  - Severity badge uses the correct colour variant for RED/AMBER/GREEN
  - FindingCard renders all three fields independently
  - Citation field is optional; absence does not break rendering

No Reflex server or live API is used. Tests operate on the FindingItem
dataclass and the SEVERITY_COLOUR / FINDING_TYPE_LABELS mappings from conftest.
"""

from __future__ import annotations

import pytest

from .conftest import (
    FINDING_TYPE_LABELS,
    SEVERITY_COLOUR,
    FindingItem,
    MockAppState,
    ReviewPayload,
    ReviewSummary,
)
from contexta.models.enums import ConfidenceEnum, ReviewDimensionEnum


# ── Required field presence ───────────────────────────────────────────────────


def test_finding_card_has_required_fields(
    state_with_review: MockAppState,
) -> None:
    """Every FindingItem in review_payload.findings has all required fields."""
    assert state_with_review.review_payload is not None
    for finding in state_with_review.review_payload.findings:
        assert finding.finding_id is not None
        assert isinstance(finding.type, str) and finding.type
        assert finding.severity in ("RED", "AMBER", "GREEN")
        assert isinstance(finding.text, str)
        assert isinstance(finding.source_artifact, str)


def test_finding_card_renders_type_field(
    state_with_review: MockAppState,
) -> None:
    """FindingCard type field matches the FindingItem.type value."""
    findings = state_with_review.review_payload.findings
    assert findings[0].type == "Risk"
    assert findings[1].type == "Architecture"
    assert findings[2].type == "NFR"


def test_finding_card_renders_severity_field(
    state_with_review: MockAppState,
) -> None:
    """FindingCard severity field matches the FindingItem.severity value."""
    findings = state_with_review.review_payload.findings
    assert findings[0].severity == "RED"
    assert findings[1].severity == "AMBER"
    assert findings[2].severity == "GREEN"


def test_finding_card_renders_text_body(
    state_with_review: MockAppState,
) -> None:
    """FindingCard text body matches FindingItem.text."""
    findings = state_with_review.review_payload.findings
    assert "aggressive" in findings[0].text
    assert "DR strategy" in findings[1].text
    assert "Performance" in findings[2].text


def test_finding_card_renders_source_artifact(
    state_with_review: MockAppState,
) -> None:
    """FindingCard source_artifact field matches FindingItem.source_artifact."""
    findings = state_with_review.review_payload.findings
    assert findings[0].source_artifact == "scope.md"
    assert findings[1].source_artifact == "architecture.md"
    assert findings[2].source_artifact == "nfr.md"


# ── Type badge — correct label per enum value ─────────────────────────────────


@pytest.mark.parametrize("dim_value", [d.value for d in ReviewDimensionEnum])
def test_type_badge_label_for_all_dimension_enum_values(dim_value: str) -> None:
    """FINDING_TYPE_LABELS covers every ReviewDimensionEnum value."""
    assert dim_value in FINDING_TYPE_LABELS, (
        f"Missing label for ReviewDimensionEnum.{dim_value}"
    )


def test_type_badge_label_matches_enum_value() -> None:
    """The badge label for each dimension is exactly its enum string value."""
    for dim in ReviewDimensionEnum:
        assert FINDING_TYPE_LABELS[dim.value] == dim.value


# ── Severity badge — correct colour variant ───────────────────────────────────


@pytest.mark.parametrize(
    "severity,expected_colour",
    [
        ("RED", "red"),
        ("AMBER", "orange"),
        ("GREEN", "green"),
    ],
)
def test_severity_badge_colour(severity: str, expected_colour: str) -> None:
    """SEVERITY_COLOUR maps each ConfidenceEnum value to the correct UI colour."""
    assert SEVERITY_COLOUR[severity] == expected_colour


def test_severity_colour_covers_all_confidence_enum_values() -> None:
    """SEVERITY_COLOUR has an entry for every ConfidenceEnum value."""
    for conf in ConfidenceEnum:
        assert conf.value in SEVERITY_COLOUR, (
            f"Missing colour mapping for ConfidenceEnum.{conf.value}"
        )


def test_severity_badge_red_finding(state_with_review: MockAppState) -> None:
    """A RED finding resolves to the 'red' colour variant."""
    finding = state_with_review.review_payload.findings[0]
    assert finding.severity == "RED"
    assert SEVERITY_COLOUR[finding.severity] == "red"


def test_severity_badge_amber_finding(state_with_review: MockAppState) -> None:
    """An AMBER finding resolves to the 'orange' colour variant."""
    finding = state_with_review.review_payload.findings[1]
    assert finding.severity == "AMBER"
    assert SEVERITY_COLOUR[finding.severity] == "orange"


def test_severity_badge_green_finding(state_with_review: MockAppState) -> None:
    """A GREEN finding resolves to the 'green' colour variant."""
    finding = state_with_review.review_payload.findings[2]
    assert finding.severity == "GREEN"
    assert SEVERITY_COLOUR[finding.severity] == "green"


# ── Citation is optional ──────────────────────────────────────────────────────


def test_finding_card_citation_is_optional() -> None:
    """FindingItem with citation=None does not break field access."""
    finding = FindingItem(
        finding_id="0",
        type="Risk",
        severity="AMBER",
        text="Some risk text.",
        source_artifact="doc.md",
        citation=None,
    )
    assert finding.citation is None
    # All required rendering fields still accessible.
    assert finding.type == "Risk"
    assert finding.severity == "AMBER"
    assert finding.text == "Some risk text."
    assert finding.source_artifact == "doc.md"


def test_finding_card_with_citation_object() -> None:
    """FindingItem with a populated citation exposes its file_path."""
    citation = {
        "file_path": "scope.md",
        "line_start": 10,
        "line_end": 15,
        "citation_type": "Direct Reference",
        "excerpt": "Delivery in 6 months.",
    }
    finding = FindingItem(
        finding_id="1",
        type="Delivery",
        severity="RED",
        text="Tight delivery window.",
        source_artifact="scope.md",
        citation=citation,
    )
    assert finding.citation is not None
    assert finding.citation["file_path"] == "scope.md"
    assert finding.citation["line_start"] == 10


# ── Review payload summary counts ────────────────────────────────────────────


def test_review_summary_counts_are_integers(
    state_with_review: MockAppState,
) -> None:
    """All ReviewSummary fields are non-negative integers."""
    s = state_with_review.review_payload.summary
    for field_name in ("risks", "constraints", "dependencies", "assumptions", "action_items"):
        val = getattr(s, field_name)
        assert isinstance(val, int), f"{field_name} should be int, got {type(val)}"
        assert val >= 0


def test_review_summary_has_all_five_fields(
    state_with_review: MockAppState,
) -> None:
    """ReviewSummary exposes all five count fields expected by the UI."""
    s = state_with_review.review_payload.summary
    assert hasattr(s, "risks")
    assert hasattr(s, "constraints")
    assert hasattr(s, "dependencies")
    assert hasattr(s, "assumptions")
    assert hasattr(s, "action_items")


# ── Finding list completeness ─────────────────────────────────────────────────


def test_review_payload_findings_is_list(state_with_review: MockAppState) -> None:
    """review_payload.findings is always a list."""
    assert isinstance(state_with_review.review_payload.findings, list)


def test_review_payload_findings_count(state_with_review: MockAppState) -> None:
    """The mock review has exactly 3 findings."""
    assert len(state_with_review.review_payload.findings) == 3


def test_empty_findings_list_valid() -> None:
    """ReviewPayload with an empty findings list is valid."""
    payload = ReviewPayload(
        review_id="r1",
        project_id="p1",
        version_id="v1",
        status="complete",
        run_date="2024-01-01T00:00:00+00:00",
        persona="[]",
        findings=[],
        summary=ReviewSummary(),
    )
    assert payload.findings == []
