"""ProposalValidator — 6-Gate Veto Pipeline — Sprint 5.

Every gate is implemented as an individual public method so it can be
called and tested in isolation.  The ``validate()`` orchestrator runs all
six gates in sequence and aggregates the results into a
``JudgeValidationReport``.

Gate Summary
------------
1. Traceability Density   — proposal_text must contain ≥1 [X:Y] citation.
2. Contradiction Check    — proposal must not echo known arbitrator conflicts.
3. Dimensional Coverage   — proposal must address ≥6 of the 12 dimensions.
4. Diagram Alignment      — diagram_metadata present → proposal mentions diagrams.
5. Steering Compliance    — ERD present when matrix has any RED dimension.
6. Relevance Check        — ≤20% of sentences are generic filler without citations.
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..models.enums import ReviewDimensionEnum
from ..models.proposal import (
    ConfidenceMatrix,
    JudgeValidationReport,
    ProposalReport,
    ValidationGateResult,
)

# ── Constants ─────────────────────────────────────────────────────────────────

#: Regex matching [ArtifactID:SectionID] traceability references.
_CITATION_RE = re.compile(r"\[[^\]]+:[^\]]+\]")

#: Regex patterns that flag a sentence as generic filler.
#: A sentence is filler if it matches one of these AND has no citation.
_FILLER_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bIn SDLC\b", re.IGNORECASE),
    re.compile(r"\bITIL phase\b", re.IGNORECASE),
    re.compile(r"\bGenerally speaking\b", re.IGNORECASE),
    re.compile(r"\bTypically[,\s]", re.IGNORECASE),
    re.compile(r"\bIt is common practice\b", re.IGNORECASE),
    re.compile(r"\bIndustry standard\b", re.IGNORECASE),
    re.compile(r"\bBest practice\b", re.IGNORECASE),
    re.compile(r"\bIn general[,\s]", re.IGNORECASE),
    re.compile(r"\bAs a rule\b", re.IGNORECASE),
    re.compile(r"\bMost organizations\b", re.IGNORECASE),
    re.compile(r"\bMany companies\b", re.IGNORECASE),
    re.compile(r"\bIn most (projects|cases|scenarios)\b", re.IGNORECASE),
]

#: Minimum fraction of proposal sentences that must have a citation or be
#: non-filler for Gate 6 to pass.  Complement of the 0.20 filler threshold.
_MAX_FILLER_RATIO: float = 0.20

#: Minimum number of ReviewDimensionEnum names that must appear in the
#: proposal_text for Gate 3 to pass.
_MIN_DIMENSION_COVERAGE: int = 6


# ── Validator ─────────────────────────────────────────────────────────────────


class ProposalValidator:
    """Runs the 6-Gate veto pipeline against a ``ProposalReport``.

    All gate methods are public and accept only the data they need so they
    can be exercised in isolation from a test.
    """

    # ── Gate 1 ────────────────────────────────────────────────────────────────

    def gate_1_traceability_density(
        self,
        report: ProposalReport,
    ) -> ValidationGateResult:
        """Gate 1: proposal_text must contain at least one [ArtifactID:SectionID] citation.

        A proposal with zero traceability references cannot be verified
        against source material and is automatically rejected.

        Parameters
        ----------
        report:
            The ``ProposalReport`` to evaluate.

        Returns
        -------
        ValidationGateResult
            Passes when ≥1 citation pattern is found; fails otherwise.
        """
        citations = _CITATION_RE.findall(report.proposal_text)
        if citations:
            return ValidationGateResult(
                gate_number=1,
                gate_name="Traceability Density",
                passed=True,
            )
        return ValidationGateResult(
            gate_number=1,
            gate_name="Traceability Density",
            passed=False,
            reason=(
                "No [ArtifactID:SectionID] citations found in proposal_text. "
                "Every claim must be traceable to source material."
            ),
        )

    # ── Gate 2 ────────────────────────────────────────────────────────────────

    def gate_2_contradiction_check(
        self,
        report: ProposalReport,
        contradictions: List[dict],
    ) -> ValidationGateResult:
        """Gate 2: Proposal must not directly echo known arbitrator contradictions.

        Checks whether any contradiction description from the arbitrator
        appears verbatim (case-insensitive) in the proposal text, which
        would indicate the model reproduced unresolved conflicts rather than
        resolving them.

        Parameters
        ----------
        report:
            The ``ProposalReport`` to evaluate.
        contradictions:
            List of contradiction dicts from ``ArbitratorResult.contradictions``.
            Each dict has a ``"description"`` key.

        Returns
        -------
        ValidationGateResult
            Passes when no contradiction description is echoed verbatim;
            fails on first match.
        """
        if not contradictions:
            return ValidationGateResult(
                gate_number=2,
                gate_name="Contradiction Check",
                passed=True,
            )

        text_lower = report.proposal_text.lower()
        for contradiction in contradictions:
            description = contradiction.get("description", "")
            # Check a meaningful 6-word window to avoid false positives on
            # single common words while still catching verbatim echoes.
            words = description.lower().split()
            if len(words) >= 6:
                fragment = " ".join(words[:6])
                if fragment in text_lower:
                    return ValidationGateResult(
                        gate_number=2,
                        gate_name="Contradiction Check",
                        passed=False,
                        reason=(
                            f"Proposal echoes an unresolved arbitrator contradiction: "
                            f"'{description[:120]}...'"
                        ),
                    )

        return ValidationGateResult(
            gate_number=2,
            gate_name="Contradiction Check",
            passed=True,
        )

    # ── Gate 3 ────────────────────────────────────────────────────────────────

    def gate_3_dimensional_coverage(
        self,
        report: ProposalReport,
    ) -> ValidationGateResult:
        """Gate 3: proposal_text must mention ≥6 ReviewDimensionEnum names.

        A comprehensive proposal must address the multi-dimensional review
        findings.  Proposals that mention fewer than 6 dimension names are
        considered insufficiently scoped.

        Parameters
        ----------
        report:
            The ``ProposalReport`` to evaluate.

        Returns
        -------
        ValidationGateResult
            Passes when ≥6 dimension names appear; fails otherwise.
        """
        text_lower = report.proposal_text.lower()
        covered = [
            dim
            for dim in ReviewDimensionEnum
            if dim.value.lower() in text_lower
        ]
        count = len(covered)
        if count >= _MIN_DIMENSION_COVERAGE:
            return ValidationGateResult(
                gate_number=3,
                gate_name="Dimensional Coverage",
                passed=True,
            )
        missing = [
            d.value for d in ReviewDimensionEnum if d not in covered
        ]
        return ValidationGateResult(
            gate_number=3,
            gate_name="Dimensional Coverage",
            passed=False,
            reason=(
                f"Proposal mentions only {count}/{len(list(ReviewDimensionEnum))} "
                f"dimensions (minimum {_MIN_DIMENSION_COVERAGE} required). "
                f"Missing: {', '.join(missing[:6])}."
            ),
        )

    # ── Gate 4 ────────────────────────────────────────────────────────────────

    def gate_4_diagram_alignment(
        self,
        report: ProposalReport,
    ) -> ValidationGateResult:
        """Gate 4: If diagram_metadata is present, proposal_text must reference diagrams.

        A proposal that includes diagram artefacts but never refers to them
        in the text is structurally misaligned.

        Parameters
        ----------
        report:
            The ``ProposalReport`` to evaluate.

        Returns
        -------
        ValidationGateResult
            Passes if diagram_metadata is empty, or if proposal_text
            contains a diagram reference keyword; fails otherwise.
        """
        if not report.diagram_metadata:
            return ValidationGateResult(
                gate_number=4,
                gate_name="Diagram Alignment",
                passed=True,
            )

        diagram_keywords = ["diagram", "architecture diagram", "draw.io", "figure", "illustration"]
        text_lower = report.proposal_text.lower()
        if any(kw in text_lower for kw in diagram_keywords):
            return ValidationGateResult(
                gate_number=4,
                gate_name="Diagram Alignment",
                passed=True,
            )

        return ValidationGateResult(
            gate_number=4,
            gate_name="Diagram Alignment",
            passed=False,
            reason=(
                "diagram_metadata is present but proposal_text contains no "
                "reference to a diagram, figure, or draw.io artefact."
            ),
        )

    # ── Gate 5 ────────────────────────────────────────────────────────────────

    def gate_5_steering_compliance(
        self,
        report: ProposalReport,
        matrix: ConfidenceMatrix,
    ) -> ValidationGateResult:
        """Gate 5: executive_risk_disclosure must be present when matrix has RED.

        When any SDLC/ITIL phase scores RED, the proposal MUST include an
        Executive Risk Disclosure section with specific citations.  Omitting
        it while RED scores exist is a veto-level failure.

        Parameters
        ----------
        report:
            The ``ProposalReport`` to evaluate.
        matrix:
            The ``ConfidenceMatrix`` used to generate the proposal.

        Returns
        -------
        ValidationGateResult
            Passes if no RED scores exist, or if ERD is present and non-empty.
            Fails if RED scores exist but ERD is absent or empty.
        """
        if not matrix.has_red:
            return ValidationGateResult(
                gate_number=5,
                gate_name="Steering Compliance",
                passed=True,
            )

        erd = report.executive_risk_disclosure
        if erd is not None and erd.items:
            return ValidationGateResult(
                gate_number=5,
                gate_name="Steering Compliance",
                passed=True,
            )

        red_names = ", ".join(d.value for d in matrix.red_dimensions)
        return ValidationGateResult(
            gate_number=5,
            gate_name="Steering Compliance",
            passed=False,
            reason=(
                f"ConfidenceMatrix contains RED-scored dimensions "
                f"({red_names}) but executive_risk_disclosure is absent or empty. "
                "An Executive Risk Disclosure with specific [ArtifactID:SectionID] "
                "references is mandatory when any dimension scores RED."
            ),
        )

    # ── Gate 6 ────────────────────────────────────────────────────────────────

    def gate_6_relevance_check(
        self,
        report: ProposalReport,
    ) -> ValidationGateResult:
        """Gate 6: Reject if >20% of sentences are generic filler without citations.

        A sentence is classified as filler if:
        1. It matches one of the ``_FILLER_PATTERNS`` (generic industry language), AND
        2. It contains no ``[ArtifactID:SectionID]`` citation.

        Parameters
        ----------
        report:
            The ``ProposalReport`` to evaluate.

        Returns
        -------
        ValidationGateResult
            Passes when filler ratio ≤ 0.20; fails when filler ratio > 0.20.
        """
        # Split on sentence-ending punctuation followed by whitespace or end.
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", report.proposal_text)
            if s.strip()
        ]

        if not sentences:
            return ValidationGateResult(
                gate_number=6,
                gate_name="Relevance Check",
                passed=True,
            )

        filler_count = 0
        for sentence in sentences:
            has_citation = bool(_CITATION_RE.search(sentence))
            if has_citation:
                continue
            is_filler = any(pattern.search(sentence) for pattern in _FILLER_PATTERNS)
            if is_filler:
                filler_count += 1

        filler_ratio = filler_count / len(sentences)

        if filler_ratio <= _MAX_FILLER_RATIO:
            return ValidationGateResult(
                gate_number=6,
                gate_name="Relevance Check",
                passed=True,
            )

        return ValidationGateResult(
            gate_number=6,
            gate_name="Relevance Check",
            passed=False,
            reason=(
                f"Filler ratio {filler_ratio:.1%} exceeds the 20% threshold "
                f"({filler_count} of {len(sentences)} sentences are generic "
                "industry language without project-specific citations)."
            ),
        )

    # ── Orchestrator ──────────────────────────────────────────────────────────

    def validate(
        self,
        report: ProposalReport,
        matrix: ConfidenceMatrix,
        contradictions: Optional[List[dict]] = None,
    ) -> JudgeValidationReport:
        """Run all 6 gates and return an aggregated ``JudgeValidationReport``.

        Gates are executed in order (1–6).  All gates run regardless of
        earlier failures so the caller receives a complete picture.

        Parameters
        ----------
        report:
            The ``ProposalReport`` to validate.
        matrix:
            The ``ConfidenceMatrix`` used during proposal generation.
        contradictions:
            Optional list of contradiction dicts from the Arbitrator.
            Defaults to an empty list when omitted.

        Returns
        -------
        JudgeValidationReport
            ``overall_passed`` is ``True`` only when every gate passes.
            ``rejection_reason`` contains the first failing gate's reason.
        """
        if contradictions is None:
            contradictions = []

        gates = [
            self.gate_1_traceability_density(report),
            self.gate_2_contradiction_check(report, contradictions),
            self.gate_3_dimensional_coverage(report),
            self.gate_4_diagram_alignment(report),
            self.gate_5_steering_compliance(report, matrix),
            self.gate_6_relevance_check(report),
        ]

        failed = [g for g in gates if not g.passed]
        overall_passed = not bool(failed)
        rejection_reason = failed[0].reason if failed else None

        return JudgeValidationReport(
            gates=gates,
            overall_passed=overall_passed,
            rejection_reason=rejection_reason,
        )
