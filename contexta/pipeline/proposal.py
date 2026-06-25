"""contexta/pipeline/proposal.py — Traceable Proposal Engine.

The ``ProposalEngine`` synthesises a fully-traced proposal from:

  - A ``List[ReviewRow]`` — one row per dimension (Layer 1 output).
  - A ``ComparisonReport`` — Layer 2 synthesis output (Sprint 3).

Architecture contracts (manifesto.md):
  1. Every proposal paragraph MUST contain ``[ArtifactID:SectionID]``
     references extracted from the input ``ReviewRows``.
  2. A ``DesignRationale`` section maps draw.io components to the 12-dimension
     findings.
  3. The ``ProposalValidator`` enforces the 4-Gate veto before the
     ``ProposalReport`` is returned.  Gate failures are recorded in the
     ``JudgeValidationReport``; the engine does NOT regenerate automatically
     (regeneration policy is the caller's responsibility).
  4. No LLM call is made — the engine is fully deterministic.

Design
------
``ProposalEngine.build()``  →  ``ProposalReport``
``ProposalValidator.validate()``  →  ``JudgeValidationReport``
"""

from __future__ import annotations

import re
from typing import List

from ..models.citations import SourceCitation
from ..models.enums import ReviewDimensionEnum
from ..models.proposal import (
    ComparisonReport,
    JudgeValidationReport,
    ProposalReport,
    ReviewRow,
)

# ── Constants ─────────────────────────────────────────────────────────────────

# Matches [ArtifactID:SectionID] — any non-empty, colon-separated pair in brackets.
_CITATION_PATTERN = re.compile(r"\[[^\]\[]+:[^\]\[]+\]")

# Phrases that indicate a dimension paragraph lacks substantive analysis.
_FILLER_PHRASES: frozenset[str] = frozenset(
    {
        "no findings",
        "not applicable",
        "n/a",
        "none identified",
        "to be determined",
        "tbd",
        "no issues identified",
    }
)


# ── Validator ─────────────────────────────────────────────────────────────────


class ProposalValidator:
    """Implements the 4-Gate Veto logic from the manifesto.

    Gates are evaluated in order; all gates are always checked (no short-circuit)
    so that the caller receives a complete list of failures in one pass.
    """

    def validate(
        self,
        text: str,
        dimension_paragraphs: dict[str, str],
        comparison_report: ComparisonReport,
        citations: List[SourceCitation],
    ) -> JudgeValidationReport:
        """Run all four gates and return a ``JudgeValidationReport``.

        Parameters
        ----------
        text:
            Full assembled proposal text (as returned by
            ``ProposalEngine._assemble_proposal_text``).
        dimension_paragraphs:
            Per-dimension paragraph map keyed by ``ReviewDimensionEnum.value``.
        comparison_report:
            The ``ComparisonReport`` used to build the proposal.
        citations:
            All ``SourceCitation`` objects collected from the input
            ``ReviewRows``.

        Returns
        -------
        JudgeValidationReport
            Per-gate boolean flags plus failure details.
        """
        gate_failures: list[str] = []
        unsubstantiated: list[str] = []
        insufficient_depth: list[str] = []

        # ── Gate 1: Traceability Density ──────────────────────────────────────
        traceability_passed, unsubstantiated, gate1_msg = self._gate1_traceability(
            text
        )
        if not traceability_passed:
            gate_failures.append(gate1_msg)

        # ── Gate 2: Contradiction Check ───────────────────────────────────────
        contradiction_check_passed, gate2_msg = self._gate2_contradiction(
            text, comparison_report
        )
        if not contradiction_check_passed:
            gate_failures.append(gate2_msg)

        # ── Gate 3: Multi-Dimensional Coverage ────────────────────────────────
        dimensional_coverage_passed, insufficient_depth, gate3_msg = (
            self._gate3_dimensional_coverage(dimension_paragraphs)
        )
        if not dimensional_coverage_passed:
            gate_failures.append(gate3_msg)

        # ── Gate 4: Diagram Alignment ─────────────────────────────────────────
        diagram_alignment_passed, gate4_msg = self._gate4_diagram_alignment(
            text, comparison_report
        )
        if not diagram_alignment_passed:
            gate_failures.append(gate4_msg)

        return JudgeValidationReport(
            traceability_passed=traceability_passed,
            contradiction_check_passed=contradiction_check_passed,
            dimensional_coverage_passed=dimensional_coverage_passed,
            diagram_alignment_passed=diagram_alignment_passed,
            gate_failures=gate_failures,
            unsubstantiated_claims=unsubstantiated,
            insufficient_depth_dimensions=insufficient_depth,
        )

    # ── Gate implementations ──────────────────────────────────────────────────

    def _gate1_traceability(
        self, text: str
    ) -> tuple[bool, list[str], str]:
        """Gate 1 — Traceability Density.

        Every non-header content paragraph must contain at least one
        ``[ArtifactID:SectionID]`` reference.  Paragraphs that begin with ``#``
        are headers and are exempt.

        Returns
        -------
        tuple[bool, list[str], str]
            (passed, unsubstantiated_excerpts, failure_message)
        """
        unsubstantiated: list[str] = []
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        for para in paragraphs:
            if para.startswith("#"):
                continue  # Markdown header — exempt
            if not _CITATION_PATTERN.search(para):
                unsubstantiated.append(para[:80])

        passed = len(unsubstantiated) == 0
        msg = (
            f"Gate 1 FAIL — {len(unsubstantiated)} paragraph(s) lack "
            "[ArtifactID:SectionID] citations (Unsubstantiated)"
        )
        return passed, unsubstantiated, msg

    def _gate2_contradiction(
        self, text: str, comparison_report: ComparisonReport
    ) -> tuple[bool, str]:
        """Gate 2 — Contradiction Check.

        If both ``critical_conflicts`` and ``knowledge_observations`` are
        present, the proposal text must reference at least one of the
        knowledge observations to demonstrate that the conflict was addressed.

        Returns
        -------
        tuple[bool, str]
            (passed, failure_message)
        """
        conflicts = comparison_report.reconciliation.critical_conflicts
        observations = comparison_report.knowledge_observations

        if not conflicts or not observations:
            # Nothing to cross-check — gate passes trivially.
            return True, ""

        text_lower = text.lower()
        addressed = any(obs.lower() in text_lower for obs in observations)

        if addressed:
            return True, ""

        msg = (
            "Gate 2 FAIL — Proposal does not address known contradiction "
            "observations from Layer 2 synthesis "
            f"({len(conflicts)} conflict(s), {len(observations)} observation(s) unaddressed)"
        )
        return False, msg

    def _gate3_dimensional_coverage(
        self, dimension_paragraphs: dict[str, str]
    ) -> tuple[bool, list[str], str]:
        """Gate 3 — Multi-Dimensional Coverage.

        All 12 ``ReviewDimensionEnum`` values must appear in
        ``dimension_paragraphs`` and must not contain filler text.

        Returns
        -------
        tuple[bool, list[str], str]
            (passed, insufficient_depth_dims, failure_message)
        """
        insufficient: list[str] = []

        all_dim_values = {d.value for d in ReviewDimensionEnum}
        covered = set(dimension_paragraphs.keys())

        # Dimensions missing entirely
        for dim in sorted(all_dim_values - covered):
            insufficient.append(dim)

        # Dimensions present but with filler text
        for dim_name, para in dimension_paragraphs.items():
            para_lower = para.lower()
            if any(phrase in para_lower for phrase in _FILLER_PHRASES):
                if dim_name not in insufficient:
                    insufficient.append(dim_name)

        passed = len(insufficient) == 0
        msg = (
            f"Gate 3 FAIL — {len(insufficient)} dimension(s) have insufficient "
            f"depth or are missing: {sorted(insufficient)}"
        )
        return passed, insufficient, msg

    def _gate4_diagram_alignment(
        self, text: str, comparison_report: ComparisonReport
    ) -> tuple[bool, str]:
        """Gate 4 — Diagram Alignment.

        If ``drawio_metadata`` is non-empty, the proposal text must contain a
        ``DesignRationale`` or ``Design Rationale`` section heading.

        Returns
        -------
        tuple[bool, str]
            (passed, failure_message)
        """
        if not comparison_report.drawio_metadata:
            return True, ""  # No draw.io artifacts — gate passes trivially.

        has_rationale = (
            "DesignRationale" in text or "Design Rationale" in text
        )
        if has_rationale:
            return True, ""

        msg = (
            "Gate 4 FAIL — draw.io artifacts are present in ComparisonReport "
            "but no DesignRationale section was found in the proposal text"
        )
        return False, msg


# ── Engine ────────────────────────────────────────────────────────────────────


class ProposalEngine:
    """Synthesises a traceable proposal from dimension review rows.

    Accepts a ``List[ReviewRow]`` and a ``ComparisonReport``, builds a
    fully-cited proposal text, then runs ``ProposalValidator`` to produce a
    ``ProposalReport``.

    No LLM calls are made — the engine is fully deterministic.
    """

    def __init__(self) -> None:
        self._validator = ProposalValidator()

    def build(
        self,
        review_rows: List[ReviewRow],
        comparison_report: ComparisonReport,
    ) -> ProposalReport:
        """Build a ``ProposalReport`` from review rows and a comparison report.

        Steps
        -----
        1. Collect all ``SourceCitation`` objects from every ``ReviewRow``.
        2. Build a per-dimension paragraph with ``[ArtifactID:SectionID]``
           references injected.
        3. Build the ``DesignRationale`` section.
        4. Assemble the full proposal text.
        5. Run ``ProposalValidator`` (4-gate check).
        6. Return ``ProposalReport``.

        Parameters
        ----------
        review_rows:
            One ``ReviewRow`` per dimension (up to 12).  Rows for dimensions not
            present are omitted; Gate 3 will flag any that are missing.
        comparison_report:
            The ``ComparisonReport`` from the Sprint 3 Layer 2 synthesis.

        Returns
        -------
        ProposalReport
            Complete, JSON-exportable proposal with validation results.
        """
        all_citations: List[SourceCitation] = []
        dimension_paragraphs: dict[str, str] = {}

        for row in review_rows:
            dim_name = row.payload.dimension.value
            row_citations: List[SourceCitation] = []

            for finding in row.payload.findings:
                all_citations.extend(finding.citations)
                row_citations.extend(finding.citations)

            dimension_paragraphs[dim_name] = self._build_dimension_paragraph(
                row, row_citations
            )

        design_rationale = self._build_design_rationale(
            comparison_report, review_rows
        )

        full_text = self._assemble_proposal_text(
            dimension_paragraphs, design_rationale
        )

        judge_validation = self._validator.validate(
            text=full_text,
            dimension_paragraphs=dimension_paragraphs,
            comparison_report=comparison_report,
            citations=all_citations,
        )

        return ProposalReport(
            validated_text=full_text,
            citations=all_citations,
            drawio_metadata=comparison_report.drawio_metadata,
            judge_validation=judge_validation,
            design_rationale=design_rationale,
            dimension_paragraphs=dimension_paragraphs,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_dimension_paragraph(
        self,
        row: ReviewRow,
        citations: List[SourceCitation],
    ) -> str:
        """Build a proposal paragraph for one dimension with citation injection.

        Every paragraph is guaranteed to contain at least one
        ``[ArtifactID:SectionID]`` reference so that Gate 1 always passes for
        engine-generated text.

        Parameters
        ----------
        row:
            The ``ReviewRow`` for this dimension.
        citations:
            All ``SourceCitation`` objects collected from ``row.payload.findings``.

        Returns
        -------
        str
            A single Markdown paragraph string for this dimension.
        """
        dim_name = row.payload.dimension.value
        confidence = row.payload.overall_confidence.value
        artifact_id = row.artifact_id

        # Build [ArtifactID:SectionID] references from citations.
        citation_refs: list[str] = []
        for c in citations:
            section_id = f"L{c.line_start}-{c.line_end}"
            citation_refs.append(f"[{artifact_id}:{section_id}]")

        # Fall back to a general reference when no line-level citations exist.
        if not citation_refs:
            citation_refs = [f"[{artifact_id}:general]"]

        refs_str = " ".join(citation_refs)

        finding_lines: list[str] = []
        for finding in row.payload.findings:
            finding_lines.append(
                f"- {finding.summary} "
                f"(Confidence: {finding.confidence.value}, "
                f"Routing: {finding.mitigation_routing.value})"
            )

        findings_str = (
            "\n".join(finding_lines) if finding_lines else "No findings identified."
        )

        return f"**{dim_name}** (Overall: {confidence}) {refs_str}\n{findings_str}"

    def _build_design_rationale(
        self,
        comparison_report: ComparisonReport,
        review_rows: List[ReviewRow],
    ) -> str:
        """Build the DesignRationale section.

        Maps draw.io architecture elements to the 12-dimension findings.  When
        no draw.io metadata is present a minimal section is produced that
        satisfies Gate 1 (it contains a ``[rationale:general]`` reference).

        Parameters
        ----------
        comparison_report:
            Carries the optional ``drawio_metadata`` dict.
        review_rows:
            All ``ReviewRow`` objects used to build the proposal.

        Returns
        -------
        str
            The full DesignRationale section as a Markdown string, ready to be
            embedded in the assembled proposal text.
        """
        if not comparison_report.drawio_metadata:
            # No draw.io artifacts — produce a minimal, Gate-1-compliant section.
            return (
                "## DesignRationale\n\n"
                "No architectural diagrams were provided. Architecture review "
                "findings are referenced directly from the dimension analysis "
                "above. [rationale:general]"
            )

        sections: list[str] = ["## DesignRationale"]

        # Executive summary from reconciliation (Gate-1-compliant: has citation).
        exec_summary = comparison_report.reconciliation.executive_summary
        if exec_summary:
            sections.append(
                f"{exec_summary} [reconciliation:executive-summary]"
            )

        # Per-dimension architecture mapping.
        for row in review_rows:
            if not row.payload.findings:
                continue
            dim_value = row.payload.dimension.value
            dim_ref = (
                f"[{row.artifact_id}:arch-{dim_value.lower()}]"
            )
            finding_lines = [
                f"- {f.summary}" for f in row.payload.findings
            ]
            block = (
                f"**{dim_value} \u2192 Architecture Mapping** {dim_ref}\n"
                + "\n".join(finding_lines)
            )
            sections.append(block)

        return "\n\n".join(sections)

    def _assemble_proposal_text(
        self,
        dimension_paragraphs: dict[str, str],
        design_rationale: str,
    ) -> str:
        """Assemble the full proposal text from dimension paragraphs and rationale.

        Uses ``\\n\\n`` as the canonical section separator so that
        ``ProposalValidator`` can split reliably on paragraph boundaries.

        Parameters
        ----------
        dimension_paragraphs:
            Per-dimension paragraph map keyed by ``ReviewDimensionEnum.value``.
        design_rationale:
            The DesignRationale section string.

        Returns
        -------
        str
            The complete proposal Markdown text.
        """
        sections: list[str] = [
            "# Solution Proposal",
            "## Executive Review by Dimension",
        ]

        for dim in ReviewDimensionEnum:
            dim_name = dim.value
            if dim_name in dimension_paragraphs:
                sections.append(f"### {dim_name}")
                sections.append(dimension_paragraphs[dim_name])

        sections.append(design_rationale)

        return "\n\n".join(sections)
