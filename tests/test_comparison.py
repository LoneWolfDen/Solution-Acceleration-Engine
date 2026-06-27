"""Tests for contexta/pipeline/comparison.py.

Coverage areas
--------------
- ReviewRow helpers (payload indexing).
- Identical-review baseline (no changes).
- Confidence-shift detection per direction.
- Risk improvement / degradation lists.
- Artifact add / remove set logic.
- Finding-level diff (added / removed summaries).
- Citation key format and set diff.
- Partial dimension coverage (missing dimension skipped).
- JSON serialisation and round-trip.
- generated_at timestamp format.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

import pytest

from contexta.models.citations import SourceCitation
from contexta.models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from contexta.models.findings import IssueFinding
from contexta.models.payloads import ReviewNodePayload
from contexta.pipeline.comparison import (
    ComparisonManager,
    ComparisonReport,
    DimensionDiff,
    ReviewRow,
    _citation_key,
    _risk_direction,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _citation(file_path: str, start: int, end: int) -> SourceCitation:
    return SourceCitation(
        file_path=file_path,
        line_start=start,
        line_end=end,
        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
        excerpt="excerpt",
    )


def _finding(
    dim: ReviewDimensionEnum,
    confidence: ConfidenceEnum,
    summary: str,
    citations: Optional[List[SourceCitation]] = None,
) -> IssueFinding:
    return IssueFinding(
        dimension=dim,
        confidence=confidence,
        summary=summary,
        detail="detail",
        citations=citations or [],
        mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
    )


def _payload(
    dim: ReviewDimensionEnum,
    overall: ConfidenceEnum,
    findings: Optional[List[IssueFinding]] = None,
) -> ReviewNodePayload:
    return ReviewNodePayload(
        dimension=dim,
        findings=findings or [],
        overall_confidence=overall,
        raw_llm_response="{}",
    )


def _full_row(
    node_id: str = "node-a",
    node_name: str = "Review A",
    confidences: Optional[Dict[ReviewDimensionEnum, ConfidenceEnum]] = None,
    artifacts: Optional[List[str]] = None,
    findings_map: Optional[Dict[ReviewDimensionEnum, List[IssueFinding]]] = None,
) -> ReviewRow:
    """Build a ReviewRow with all 12 dimensions populated."""
    confidences = confidences or {}
    findings_map = findings_map or {}
    payloads = [
        _payload(
            dim,
            confidences.get(dim, ConfidenceEnum.AMBER),
            findings_map.get(dim, []),
        )
        for dim in ReviewDimensionEnum
    ]
    return ReviewRow(
        node_id=node_id,
        node_name=node_name,
        artifacts=artifacts or [],
        payloads=payloads,
    )


# ── TestReviewRowHelpers ──────────────────────────────────────────────────────

class TestReviewRowHelpers:
    def test_payload_by_dimension_returns_dict(self):
        row = _full_row()
        result = row.payload_by_dimension()
        assert isinstance(result, dict)

    def test_payload_by_dimension_covers_all_12(self):
        row = _full_row()
        result = row.payload_by_dimension()
        assert set(result.keys()) == set(ReviewDimensionEnum)

    def test_payload_by_dimension_values_are_payloads(self):
        row = _full_row()
        for val in row.payload_by_dimension().values():
            assert isinstance(val, ReviewNodePayload)

    def test_payload_by_dimension_key_matches_payload_dimension(self):
        row = _full_row()
        for dim, payload in row.payload_by_dimension().items():
            assert payload.dimension == dim

    def test_empty_artifacts_list(self):
        row = ReviewRow(node_id="x", node_name="y", artifacts=[], payloads=[])
        assert row.artifacts == []

    def test_node_id_and_name_stored(self):
        row = ReviewRow(node_id="id-1", node_name="Name 1", artifacts=[], payloads=[])
        assert row.node_id == "id-1"
        assert row.node_name == "Name 1"


# ── TestCitationKeyHelper ─────────────────────────────────────────────────────

class TestCitationKeyHelper:
    def test_format_is_bracket_path_colon_range(self):
        cit = _citation("/proposal.md", 5, 10)
        assert _citation_key(cit) == "[/proposal.md:5-10]"

    def test_single_line_citation(self):
        cit = _citation("/sow.md", 42, 42)
        assert _citation_key(cit) == "[/sow.md:42-42]"

    def test_different_file_paths(self):
        cit = _citation("/docs/arch.md", 1, 100)
        assert _citation_key(cit) == "[/docs/arch.md:1-100]"

    def test_citation_key_is_string(self):
        cit = _citation("/f.md", 1, 2)
        assert isinstance(_citation_key(cit), str)

    def test_unique_keys_for_different_ranges(self):
        k1 = _citation_key(_citation("/f.md", 1, 5))
        k2 = _citation_key(_citation("/f.md", 6, 10))
        assert k1 != k2


# ── TestRiskDirectionHelper ───────────────────────────────────────────────────

class TestRiskDirectionHelper:
    def test_red_to_green_is_improved(self):
        assert _risk_direction(ConfidenceEnum.RED, ConfidenceEnum.GREEN) == "IMPROVED"

    def test_green_to_red_is_degraded(self):
        assert _risk_direction(ConfidenceEnum.GREEN, ConfidenceEnum.RED) == "DEGRADED"

    def test_same_confidence_is_unchanged(self):
        for conf in ConfidenceEnum:
            assert _risk_direction(conf, conf) == "UNCHANGED"

    def test_amber_to_green_is_improved(self):
        assert _risk_direction(ConfidenceEnum.AMBER, ConfidenceEnum.GREEN) == "IMPROVED"

    def test_red_to_amber_is_improved(self):
        assert _risk_direction(ConfidenceEnum.RED, ConfidenceEnum.AMBER) == "IMPROVED"

    def test_green_to_amber_is_degraded(self):
        assert _risk_direction(ConfidenceEnum.GREEN, ConfidenceEnum.AMBER) == "DEGRADED"

    def test_amber_to_red_is_degraded(self):
        assert _risk_direction(ConfidenceEnum.AMBER, ConfidenceEnum.RED) == "DEGRADED"


# ── TestComparisonManagerIdentical ───────────────────────────────────────────

class TestComparisonManagerIdentical:
    """Comparing two identical ReviewRow snapshots should yield no changes."""

    def setup_method(self):
        self.manager = ComparisonManager()
        self.row = _full_row(node_id="a", node_name="A")
        self.report = self.manager.compare(self.row, self.row)

    def test_returns_comparison_report(self):
        assert isinstance(self.report, ComparisonReport)

    def test_dimension_diffs_count_is_12(self):
        assert len(self.report.dimension_diffs) == 12

    def test_no_confidence_shifted(self):
        for diff in self.report.dimension_diffs:
            assert diff.confidence_shifted is False

    def test_all_risk_direction_unchanged(self):
        for diff in self.report.dimension_diffs:
            assert diff.risk_direction == "UNCHANGED"

    def test_risk_improvements_empty(self):
        assert self.report.risk_improvements == []

    def test_risk_degradations_empty(self):
        assert self.report.risk_degradations == []

    def test_artifacts_added_empty(self):
        assert self.report.artifacts_added == []

    def test_artifacts_removed_empty(self):
        assert self.report.artifacts_removed == []

    def test_no_added_finding_summaries(self):
        for diff in self.report.dimension_diffs:
            assert diff.added_finding_summaries == []

    def test_no_removed_finding_summaries(self):
        for diff in self.report.dimension_diffs:
            assert diff.removed_finding_summaries == []

    def test_baseline_and_current_node_ids(self):
        assert self.report.baseline_node_id == "a"
        assert self.report.current_node_id == "a"

    def test_baseline_and_current_node_names(self):
        assert self.report.baseline_node_name == "A"
        assert self.report.current_node_name == "A"


# ── TestComparisonManagerConfidenceShifts ────────────────────────────────────

class TestComparisonManagerConfidenceShifts:
    def setup_method(self):
        self.manager = ComparisonManager()

    def _compare_single_shift(
        self,
        dim: ReviewDimensionEnum,
        baseline_conf: ConfidenceEnum,
        current_conf: ConfidenceEnum,
    ) -> DimensionDiff:
        baseline = _full_row(confidences={dim: baseline_conf})
        current = _full_row(confidences={dim: current_conf})
        report = self.manager.compare(baseline, current)
        return next(d for d in report.dimension_diffs if d.dimension == dim)

    def test_red_to_green_marks_improved(self):
        diff = self._compare_single_shift(
            ReviewDimensionEnum.RISK, ConfidenceEnum.RED, ConfidenceEnum.GREEN
        )
        assert diff.risk_direction == "IMPROVED"
        assert diff.confidence_shifted is True

    def test_green_to_red_marks_degraded(self):
        diff = self._compare_single_shift(
            ReviewDimensionEnum.TIMELINE, ConfidenceEnum.GREEN, ConfidenceEnum.RED
        )
        assert diff.risk_direction == "DEGRADED"
        assert diff.confidence_shifted is True

    def test_amber_to_green_marks_improved(self):
        diff = self._compare_single_shift(
            ReviewDimensionEnum.SCOPE, ConfidenceEnum.AMBER, ConfidenceEnum.GREEN
        )
        assert diff.risk_direction == "IMPROVED"

    def test_red_to_amber_marks_improved(self):
        diff = self._compare_single_shift(
            ReviewDimensionEnum.ARCHITECTURE, ConfidenceEnum.RED, ConfidenceEnum.AMBER
        )
        assert diff.risk_direction == "IMPROVED"

    def test_green_to_amber_marks_degraded(self):
        diff = self._compare_single_shift(
            ReviewDimensionEnum.DELIVERY, ConfidenceEnum.GREEN, ConfidenceEnum.AMBER
        )
        assert diff.risk_direction == "DEGRADED"

    def test_amber_to_red_marks_degraded(self):
        diff = self._compare_single_shift(
            ReviewDimensionEnum.NFR, ConfidenceEnum.AMBER, ConfidenceEnum.RED
        )
        assert diff.risk_direction == "DEGRADED"

    def test_same_confidence_not_shifted(self):
        diff = self._compare_single_shift(
            ReviewDimensionEnum.INTENT, ConfidenceEnum.GREEN, ConfidenceEnum.GREEN
        )
        assert diff.confidence_shifted is False
        assert diff.risk_direction == "UNCHANGED"

    def test_improved_dimension_in_risk_improvements_list(self):
        baseline = _full_row(confidences={ReviewDimensionEnum.RISK: ConfidenceEnum.RED})
        current = _full_row(confidences={ReviewDimensionEnum.RISK: ConfidenceEnum.GREEN})
        report = self.manager.compare(baseline, current)
        assert ReviewDimensionEnum.RISK.value in report.risk_improvements

    def test_degraded_dimension_in_risk_degradations_list(self):
        baseline = _full_row(confidences={ReviewDimensionEnum.SCOPE: ConfidenceEnum.GREEN})
        current = _full_row(confidences={ReviewDimensionEnum.SCOPE: ConfidenceEnum.RED})
        report = self.manager.compare(baseline, current)
        assert ReviewDimensionEnum.SCOPE.value in report.risk_degradations

    def test_improved_dimension_not_in_risk_degradations(self):
        baseline = _full_row(confidences={ReviewDimensionEnum.RISK: ConfidenceEnum.RED})
        current = _full_row(confidences={ReviewDimensionEnum.RISK: ConfidenceEnum.GREEN})
        report = self.manager.compare(baseline, current)
        assert ReviewDimensionEnum.RISK.value not in report.risk_degradations

    def test_multiple_shifts_captured(self):
        baseline = _full_row(confidences={
            ReviewDimensionEnum.SCOPE: ConfidenceEnum.RED,
            ReviewDimensionEnum.RISK: ConfidenceEnum.GREEN,
        })
        current = _full_row(confidences={
            ReviewDimensionEnum.SCOPE: ConfidenceEnum.GREEN,
            ReviewDimensionEnum.RISK: ConfidenceEnum.RED,
        })
        report = self.manager.compare(baseline, current)
        assert ReviewDimensionEnum.SCOPE.value in report.risk_improvements
        assert ReviewDimensionEnum.RISK.value in report.risk_degradations

    def test_baseline_confidence_preserved_in_diff(self):
        diff = self._compare_single_shift(
            ReviewDimensionEnum.COMMERCIAL, ConfidenceEnum.RED, ConfidenceEnum.GREEN
        )
        assert diff.baseline_confidence == ConfidenceEnum.RED
        assert diff.current_confidence == ConfidenceEnum.GREEN


# ── TestComparisonManagerArtifacts ───────────────────────────────────────────

class TestComparisonManagerArtifacts:
    def setup_method(self):
        self.manager = ComparisonManager()

    def test_artifact_only_in_current_appears_in_added(self):
        baseline = _full_row(artifacts=["/a.md"])
        current = _full_row(artifacts=["/a.md", "/b.md"])
        report = self.manager.compare(baseline, current)
        assert "/b.md" in report.artifacts_added
        assert "/b.md" not in report.artifacts_removed

    def test_artifact_only_in_baseline_appears_in_removed(self):
        baseline = _full_row(artifacts=["/a.md", "/old.md"])
        current = _full_row(artifacts=["/a.md"])
        report = self.manager.compare(baseline, current)
        assert "/old.md" in report.artifacts_removed
        assert "/old.md" not in report.artifacts_added

    def test_common_artifact_not_in_either_list(self):
        baseline = _full_row(artifacts=["/shared.md"])
        current = _full_row(artifacts=["/shared.md"])
        report = self.manager.compare(baseline, current)
        assert "/shared.md" not in report.artifacts_added
        assert "/shared.md" not in report.artifacts_removed

    def test_empty_artifacts_on_both_sides(self):
        baseline = _full_row(artifacts=[])
        current = _full_row(artifacts=[])
        report = self.manager.compare(baseline, current)
        assert report.artifacts_added == []
        assert report.artifacts_removed == []

    def test_multiple_adds_and_removes(self):
        baseline = _full_row(artifacts=["/a.md", "/b.md", "/shared.md"])
        current = _full_row(artifacts=["/c.md", "/d.md", "/shared.md"])
        report = self.manager.compare(baseline, current)
        assert set(report.artifacts_added) == {"/c.md", "/d.md"}
        assert set(report.artifacts_removed) == {"/a.md", "/b.md"}

    def test_artifacts_added_is_sorted(self):
        baseline = _full_row(artifacts=[])
        current = _full_row(artifacts=["/z.md", "/a.md", "/m.md"])
        report = self.manager.compare(baseline, current)
        assert report.artifacts_added == sorted(report.artifacts_added)

    def test_artifacts_removed_is_sorted(self):
        baseline = _full_row(artifacts=["/z.md", "/a.md", "/m.md"])
        current = _full_row(artifacts=[])
        report = self.manager.compare(baseline, current)
        assert report.artifacts_removed == sorted(report.artifacts_removed)


# ── TestComparisonManagerFindings ────────────────────────────────────────────

class TestComparisonManagerFindings:
    def setup_method(self):
        self.manager = ComparisonManager()
        self.dim = ReviewDimensionEnum.RISK

    def _diff_for_dim(
        self,
        baseline_findings: List[IssueFinding],
        current_findings: List[IssueFinding],
    ) -> DimensionDiff:
        baseline = _full_row(findings_map={self.dim: baseline_findings})
        current = _full_row(findings_map={self.dim: current_findings})
        report = self.manager.compare(baseline, current)
        return next(d for d in report.dimension_diffs if d.dimension == self.dim)

    def test_new_finding_summary_in_added(self):
        baseline_f = [_finding(self.dim, ConfidenceEnum.AMBER, "old-issue")]
        current_f = [
            _finding(self.dim, ConfidenceEnum.AMBER, "old-issue"),
            _finding(self.dim, ConfidenceEnum.RED, "new-issue"),
        ]
        diff = self._diff_for_dim(baseline_f, current_f)
        assert "new-issue" in diff.added_finding_summaries

    def test_removed_finding_summary_in_removed(self):
        baseline_f = [
            _finding(self.dim, ConfidenceEnum.AMBER, "old-issue"),
            _finding(self.dim, ConfidenceEnum.RED, "gone-issue"),
        ]
        current_f = [_finding(self.dim, ConfidenceEnum.AMBER, "old-issue")]
        diff = self._diff_for_dim(baseline_f, current_f)
        assert "gone-issue" in diff.removed_finding_summaries

    def test_identical_findings_no_added_or_removed(self):
        fs = [_finding(self.dim, ConfidenceEnum.AMBER, "issue-1")]
        diff = self._diff_for_dim(fs, fs)
        assert diff.added_finding_summaries == []
        assert diff.removed_finding_summaries == []

    def test_all_findings_replaced(self):
        baseline_f = [_finding(self.dim, ConfidenceEnum.RED, "old")]
        current_f = [_finding(self.dim, ConfidenceEnum.GREEN, "new")]
        diff = self._diff_for_dim(baseline_f, current_f)
        assert "old" in diff.removed_finding_summaries
        assert "new" in diff.added_finding_summaries

    def test_empty_findings_on_both_sides(self):
        diff = self._diff_for_dim([], [])
        assert diff.added_finding_summaries == []
        assert diff.removed_finding_summaries == []

    def test_added_summaries_sorted(self):
        current_f = [
            _finding(self.dim, ConfidenceEnum.RED, "z-issue"),
            _finding(self.dim, ConfidenceEnum.RED, "a-issue"),
        ]
        diff = self._diff_for_dim([], current_f)
        assert diff.added_finding_summaries == sorted(diff.added_finding_summaries)


# ── TestComparisonManagerCitations ───────────────────────────────────────────

class TestComparisonManagerCitations:
    def setup_method(self):
        self.manager = ComparisonManager()
        self.dim = ReviewDimensionEnum.ARCHITECTURE

    def _diff_with_cites(
        self,
        baseline_cites: List[SourceCitation],
        current_cites: List[SourceCitation],
    ) -> DimensionDiff:
        bf = [_finding(self.dim, ConfidenceEnum.AMBER, "b", baseline_cites)]
        cf = [_finding(self.dim, ConfidenceEnum.AMBER, "c", current_cites)]
        baseline = _full_row(findings_map={self.dim: bf})
        current = _full_row(findings_map={self.dim: cf})
        report = self.manager.compare(baseline, current)
        return next(d for d in report.dimension_diffs if d.dimension == self.dim)

    def test_citation_key_format_preserved(self):
        cite = _citation("/sow.md", 3, 7)
        diff = self._diff_with_cites([], [cite])
        assert "[/sow.md:3-7]" in diff.new_citations

    def test_common_citation_in_common_list(self):
        cite = _citation("/shared.md", 1, 5)
        diff = self._diff_with_cites([cite], [cite])
        assert "[/shared.md:1-5]" in diff.common_citations
        assert diff.new_citations == []
        assert diff.dropped_citations == []

    def test_new_citation_not_in_dropped(self):
        cite = _citation("/new.md", 1, 2)
        diff = self._diff_with_cites([], [cite])
        assert "[/new.md:1-2]" in diff.new_citations
        assert diff.dropped_citations == []

    def test_dropped_citation_not_in_new(self):
        cite = _citation("/old.md", 5, 10)
        diff = self._diff_with_cites([cite], [])
        assert "[/old.md:5-10]" in diff.dropped_citations
        assert diff.new_citations == []

    def test_no_citations_all_lists_empty(self):
        diff = self._diff_with_cites([], [])
        assert diff.common_citations == []
        assert diff.new_citations == []
        assert diff.dropped_citations == []

    def test_multiple_citations_partitioned(self):
        shared = _citation("/shared.md", 1, 3)
        only_b = _citation("/only-b.md", 4, 6)
        only_c = _citation("/only-c.md", 7, 9)
        diff = self._diff_with_cites([shared, only_b], [shared, only_c])
        assert "[/shared.md:1-3]" in diff.common_citations
        assert "[/only-b.md:4-6]" in diff.dropped_citations
        assert "[/only-c.md:7-9]" in diff.new_citations

    def test_citation_lists_are_sorted(self):
        cites = [
            _citation("/z.md", 1, 2),
            _citation("/a.md", 1, 2),
        ]
        diff = self._diff_with_cites([], cites)
        assert diff.new_citations == sorted(diff.new_citations)


# ── TestComparisonReportJsonSerialization ────────────────────────────────────

class TestComparisonReportJsonSerialization:
    def setup_method(self):
        self.manager = ComparisonManager()
        self.baseline = _full_row("base-1", "Baseline", artifacts=["/a.md"])
        self.current = _full_row(
            "curr-1",
            "Current",
            confidences={ReviewDimensionEnum.RISK: ConfidenceEnum.GREEN},
            artifacts=["/b.md"],
        )
        self.report = self.manager.compare(self.baseline, self.current)

    def test_model_dump_json_is_valid_json(self):
        raw = self.report.model_dump_json()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_round_trip_preserves_node_ids(self):
        raw = self.report.model_dump_json()
        restored = ComparisonReport.model_validate_json(raw)
        assert restored.baseline_node_id == self.report.baseline_node_id
        assert restored.current_node_id == self.report.current_node_id

    def test_round_trip_preserves_dimension_diffs_count(self):
        raw = self.report.model_dump_json()
        restored = ComparisonReport.model_validate_json(raw)
        assert len(restored.dimension_diffs) == len(self.report.dimension_diffs)

    def test_generated_at_is_iso8601(self):
        from datetime import datetime
        datetime.fromisoformat(self.report.generated_at)  # raises if malformed

    def test_risk_improvements_preserved_in_round_trip(self):
        raw = self.report.model_dump_json()
        restored = ComparisonReport.model_validate_json(raw)
        assert restored.risk_improvements == self.report.risk_improvements

    def test_artifacts_added_preserved_in_round_trip(self):
        raw = self.report.model_dump_json()
        restored = ComparisonReport.model_validate_json(raw)
        assert restored.artifacts_added == self.report.artifacts_added

    def test_artifacts_removed_preserved_in_round_trip(self):
        raw = self.report.model_dump_json()
        restored = ComparisonReport.model_validate_json(raw)
        assert restored.artifacts_removed == self.report.artifacts_removed


# ── TestComparisonManagerPartialCoverage ─────────────────────────────────────

class TestComparisonManagerPartialCoverage:
    """Dimensions missing from either snapshot are skipped, not errored."""

    def test_missing_dimension_skipped(self):
        manager = ComparisonManager()
        # Only populate 11 dimensions (skip CONSISTENCY)
        payloads_a = [
            _payload(dim, ConfidenceEnum.AMBER)
            for dim in ReviewDimensionEnum
            if dim != ReviewDimensionEnum.CONSISTENCY
        ]
        payloads_b = list(payloads_a)
        row_a = ReviewRow(node_id="a", node_name="A", artifacts=[], payloads=payloads_a)
        row_b = ReviewRow(node_id="b", node_name="B", artifacts=[], payloads=payloads_b)
        report = manager.compare(row_a, row_b)
        # CONSISTENCY is absent from both maps — should be silently skipped.
        dims_in_report = {d.dimension for d in report.dimension_diffs}
        assert ReviewDimensionEnum.CONSISTENCY not in dims_in_report

    def test_missing_dimension_does_not_affect_others(self):
        manager = ComparisonManager()
        payloads = [
            _payload(dim, ConfidenceEnum.AMBER)
            for dim in ReviewDimensionEnum
            if dim != ReviewDimensionEnum.CONSISTENCY
        ]
        row = ReviewRow(node_id="a", node_name="A", artifacts=[], payloads=payloads)
        report = manager.compare(row, row)
        # The 11 present dimensions are still diffed correctly.
        assert len(report.dimension_diffs) == 11
