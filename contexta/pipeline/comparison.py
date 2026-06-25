"""Comparison Manager — cross-review diffing and impact analysis.

``ComparisonManager.compare()`` accepts two ``ReviewRow`` snapshots and
returns a ``ComparisonReport`` that:

- Diffs the 12-dimension output (confidence shifts, finding deltas).
- Identifies changes in the artifact set used between the two reviews.
- Highlights risk shifts (IMPROVED | DEGRADED | UNCHANGED) per dimension.

Manifesto compliance
--------------------
- All ``[ArtifactID:SectionID]`` citation references from the source
  ``ReviewNodePayload`` objects are preserved in each ``DimensionDiff``
  (``common_citations``, ``new_citations``, ``dropped_citations``).
- ``ComparisonReport`` is a pure Pydantic model; ``model_dump_json()``
  produces a fully self-contained, provenance-preserving export.
- No TUI dependencies — pure pipeline logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Set

from pydantic import BaseModel

from ..models.enums import ConfidenceEnum, ReviewDimensionEnum
from ..models.payloads import ReviewNodePayload


# ── Confidence ordering ───────────────────────────────────────────────────────

_CONFIDENCE_RANK: Dict[ConfidenceEnum, int] = {
    ConfidenceEnum.RED: 1,
    ConfidenceEnum.AMBER: 2,
    ConfidenceEnum.GREEN: 3,
}


def _risk_direction(baseline: ConfidenceEnum, current: ConfidenceEnum) -> str:
    """Return ``"IMPROVED"``, ``"DEGRADED"``, or ``"UNCHANGED"``."""
    b, c = _CONFIDENCE_RANK[baseline], _CONFIDENCE_RANK[current]
    if c > b:
        return "IMPROVED"
    if c < b:
        return "DEGRADED"
    return "UNCHANGED"


# ── Citation key helper ───────────────────────────────────────────────────────

def _citation_key(citation: object) -> str:
    """Format a ``SourceCitation`` as ``[ArtifactID:SectionID]``.

    Uses ``file_path`` as the ArtifactID and ``line_start-line_end`` as the
    SectionID, matching the traceability standard defined in the manifesto.
    """
    return f"[{citation.file_path}:{citation.line_start}-{citation.line_end}]"  # type: ignore[attr-defined]


# ── Input snapshot ────────────────────────────────────────────────────────────

@dataclass
class ReviewRow:
    """Snapshot of a completed 12-dimension review for comparison purposes.

    Attributes
    ----------
    node_id:
        UUID of the source node in the ``nodes`` table.
    node_name:
        Human-readable label for the node (e.g. ``"v1 — Initial Review"``).
    artifacts:
        File paths of every artifact ingested for this review.  Used to
        compute ``artifacts_added`` / ``artifacts_removed`` in the report.
    payloads:
        Validated ``ReviewNodePayload`` objects — one per
        ``ReviewDimensionEnum``.  Should contain exactly 12 entries for a
        complete Layer 1 run.
    """

    node_id: str
    node_name: str
    artifacts: List[str]
    payloads: List[ReviewNodePayload]

    def payload_by_dimension(self) -> Dict[ReviewDimensionEnum, ReviewNodePayload]:
        """Index payloads by dimension for O(1) lookup."""
        return {p.dimension: p for p in self.payloads}


# ── Diff models ───────────────────────────────────────────────────────────────

class DimensionDiff(BaseModel):
    """Change record for a single dimension between two review snapshots.

    All ``[ArtifactID:SectionID]`` citation references from the source
    payloads are preserved so that downstream consumers retain full
    provenance without needing to re-access the original nodes.
    """

    dimension: ReviewDimensionEnum
    baseline_confidence: ConfidenceEnum
    current_confidence: ConfidenceEnum
    confidence_shifted: bool
    risk_direction: str                      # "IMPROVED" | "DEGRADED" | "UNCHANGED"
    added_finding_summaries: List[str]       # finding summaries new in *current*
    removed_finding_summaries: List[str]     # finding summaries dropped from *baseline*
    common_citations: List[str]              # [ArtifactID:SectionID] present in both
    new_citations: List[str]                 # [ArtifactID:SectionID] added in *current*
    dropped_citations: List[str]             # [ArtifactID:SectionID] removed from *baseline*


class ComparisonReport(BaseModel):
    """JSON-exportable diff between two ``ReviewRow`` snapshots.

    Manifesto compliance
    --------------------
    - Every ``[ArtifactID:SectionID]`` reference from the source reviews is
      carried through the ``DimensionDiff`` citation sets.
    - Fully serialisable via ``model_dump_json()`` with zero provenance loss.
    - No TUI or DB imports — pure analytical output.
    """

    baseline_node_id: str
    current_node_id: str
    baseline_node_name: str
    current_node_name: str
    dimension_diffs: List[DimensionDiff]
    artifacts_added: List[str]      # file paths in *current*, absent from *baseline*
    artifacts_removed: List[str]    # file paths in *baseline*, absent from *current*
    risk_improvements: List[str]    # dimension values where overall_confidence improved
    risk_degradations: List[str]    # dimension values where overall_confidence degraded
    generated_at: str               # ISO-8601 UTC


# ── Manager ───────────────────────────────────────────────────────────────────

class ComparisonManager:
    """Diffs two ``ReviewRow`` snapshots across all 12 dimensions.

    Usage
    -----
    ::

        manager = ComparisonManager()
        report  = manager.compare(baseline_row, current_row)
        json_str = report.model_dump_json()

    The returned ``ComparisonReport`` is immutable and fully self-contained;
    no database or LLM calls are made.
    """

    def compare(self, baseline: ReviewRow, current: ReviewRow) -> ComparisonReport:
        """Compute a ``ComparisonReport`` from two review snapshots.

        Parameters
        ----------
        baseline:
            The earlier (reference) review snapshot.
        current:
            The newer (comparison target) review snapshot.

        Returns
        -------
        ComparisonReport
            Dimension-by-dimension diff, artifact change set, and risk-shift
            summary.  Fully JSON-exportable via ``model_dump_json()``.
        """
        baseline_map = baseline.payload_by_dimension()
        current_map = current.payload_by_dimension()

        dimension_diffs: List[DimensionDiff] = []
        risk_improvements: List[str] = []
        risk_degradations: List[str] = []

        for dim in ReviewDimensionEnum:
            b_payload = baseline_map.get(dim)
            c_payload = current_map.get(dim)

            if b_payload is None or c_payload is None:
                # Skip dimensions missing from either snapshot.
                continue

            b_conf = b_payload.overall_confidence
            c_conf = c_payload.overall_confidence
            shifted = b_conf != c_conf
            direction = _risk_direction(b_conf, c_conf)

            if direction == "IMPROVED":
                risk_improvements.append(dim.value)
            elif direction == "DEGRADED":
                risk_degradations.append(dim.value)

            # Finding diff — use summary as the stable identity key.
            b_summaries: Set[str] = {f.summary for f in b_payload.findings}
            c_summaries: Set[str] = {f.summary for f in c_payload.findings}
            added_summaries = sorted(c_summaries - b_summaries)
            removed_summaries = sorted(b_summaries - c_summaries)

            # Citation diff — use [ArtifactID:SectionID] as the stable key.
            b_cites: Set[str] = {
                _citation_key(cit)
                for f in b_payload.findings
                for cit in f.citations
            }
            c_cites: Set[str] = {
                _citation_key(cit)
                for f in c_payload.findings
                for cit in f.citations
            }
            common_cites = sorted(b_cites & c_cites)
            new_cites = sorted(c_cites - b_cites)
            dropped_cites = sorted(b_cites - c_cites)

            dimension_diffs.append(
                DimensionDiff(
                    dimension=dim,
                    baseline_confidence=b_conf,
                    current_confidence=c_conf,
                    confidence_shifted=shifted,
                    risk_direction=direction,
                    added_finding_summaries=added_summaries,
                    removed_finding_summaries=removed_summaries,
                    common_citations=common_cites,
                    new_citations=new_cites,
                    dropped_citations=dropped_cites,
                )
            )

        # Artifact change set.
        b_arts: Set[str] = set(baseline.artifacts)
        c_arts: Set[str] = set(current.artifacts)

        return ComparisonReport(
            baseline_node_id=baseline.node_id,
            current_node_id=current.node_id,
            baseline_node_name=baseline.node_name,
            current_node_name=current.node_name,
            dimension_diffs=dimension_diffs,
            artifacts_added=sorted(c_arts - b_arts),
            artifacts_removed=sorted(b_arts - c_arts),
            risk_improvements=risk_improvements,
            risk_degradations=risk_degradations,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
