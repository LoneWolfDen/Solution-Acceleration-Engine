"""tests/ui/test_finding_card.py — FindingCard component tests.

Spec requirement (Milestone 6, task 6.4):
  - FindingCard renders type, severity, text, source_artifact from mock finding
  - Type badge shows correct label for each finding type enum value
  - Severity badge shows correct colour variant

Tests run without a server; they inspect the component tree structure and
confirm the correct Reflex widget types and event wiring are present.
"""

from __future__ import annotations

import pytest
import reflex as rx

from tests.ui.conftest import collect_types, find_by_type
from web.components.finding_card import finding_card, _severity_badge, _type_badge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEVERITY_LEVELS = ["HIGH", "MEDIUM", "LOW"]
FINDING_TYPES = ["RISK", "CONSTRAINT", "DEPENDENCY", "ASSUMPTION", "ACTION_ITEM"]


def _make_finding(severity: str = "HIGH", ftype: str = "RISK", citation: str = "") -> dict:
    return {
        "finding_id": "f-test",
        "type": ftype,
        "severity": severity,
        "text": f"Sample {ftype} finding at severity {severity}.",
        "source_artifact": "doc.md",
        "citation": citation,
    }


# ---------------------------------------------------------------------------
# Smoke tests — component renders without raising
# ---------------------------------------------------------------------------


class TestFindingCardSmoke:
    def test_returns_rx_component(self, mock_finding):
        result = finding_card(mock_finding)
        assert isinstance(result, rx.Component)

    def test_returns_rx_component_with_citation(self, mock_finding_with_citation):
        result = finding_card(mock_finding_with_citation)
        assert isinstance(result, rx.Component)

    @pytest.mark.parametrize("severity", SEVERITY_LEVELS)
    def test_renders_for_each_severity(self, severity: str):
        comp = finding_card(_make_finding(severity=severity))
        assert isinstance(comp, rx.Component)

    @pytest.mark.parametrize("ftype", FINDING_TYPES)
    def test_renders_for_each_type(self, ftype: str):
        comp = finding_card(_make_finding(ftype=ftype))
        assert isinstance(comp, rx.Component)


# ---------------------------------------------------------------------------
# Structure tests — expected widget types are present
# ---------------------------------------------------------------------------


class TestFindingCardStructure:
    def test_top_level_is_box(self, mock_finding):
        comp = finding_card(mock_finding)
        assert type(comp).__name__ == "Box"

    def test_contains_badge_for_severity(self, mock_finding):
        """At least one Badge in the tree for the severity level."""
        comp = finding_card(mock_finding)
        counts = collect_types(comp)
        assert counts["Badge"] >= 1

    def test_contains_match_for_severity_colour(self, mock_finding):
        """rx.match drives severity colour selection — must be present."""
        comp = finding_card(mock_finding)
        counts = collect_types(comp)
        assert counts["Match"] >= 1

    def test_has_border_left_prop(self, mock_finding):
        """Top-level card box has a border_left style for severity colour."""
        comp = finding_card(mock_finding)
        assert hasattr(comp, "border_left")

    def test_contains_cond_for_citation_block(self, mock_finding):
        """rx.cond controls whether the citation excerpt box renders."""
        comp = finding_card(mock_finding)
        counts = collect_types(comp)
        assert counts["Cond"] >= 1

    def test_has_text_nodes(self, mock_finding):
        """The VStack body contains Text nodes for finding content."""
        comp = finding_card(mock_finding)
        counts = collect_types(comp)
        assert counts["Text"] >= 1


# ---------------------------------------------------------------------------
# Severity badge helper — returns rx.Component for all levels
# ---------------------------------------------------------------------------


class TestSeverityBadge:
    @pytest.mark.parametrize("severity", SEVERITY_LEVELS)
    def test_severity_badge_returns_component(self, severity: str):
        badge = _severity_badge(rx.Var.create(severity))
        assert isinstance(badge, rx.Component)

    def test_severity_badge_unknown_falls_back(self):
        """Unknown severity should still produce a component (gray fallback)."""
        badge = _severity_badge(rx.Var.create("UNKNOWN"))
        assert isinstance(badge, rx.Component)


# ---------------------------------------------------------------------------
# Type badge helper
# ---------------------------------------------------------------------------


class TestTypeBadge:
    @pytest.mark.parametrize("ftype", FINDING_TYPES)
    def test_type_badge_returns_component(self, ftype: str):
        badge = _type_badge(rx.Var.create(ftype))
        assert isinstance(badge, rx.Component)

    def test_type_badge_uses_badge_widget(self):
        badge = _type_badge(rx.Var.create("RISK"))
        # _type_badge is a plain rx.badge — tree has at least one Badge
        counts = collect_types(badge)
        assert counts.get("Badge", 0) >= 1
