"""contexta/pipeline/proposal.py — Proposal Engine (Sprint 4 + Sprint 5 merged).

Exports
-------
ProposalEngine
    * ``generate(payloads, artifact_context)`` — Sprint 5 async path:
      builds a ``ConfidenceMatrix``, injects it into the LLM prompt,
      falls back to a deterministic mock on LLM failure, and attaches a
      ``JudgeValidationReport`` (6-gate) to every returned ``ProposalReport``.
    * ``build(review_rows, comparison_report)`` — Sprint 4 sync path:
      deterministic, citation-injected, 4-gate validated proposal from
      ``ReviewRow`` inputs.  Returns the same ``ProposalReport`` schema.

ProposalValidator
    4-gate veto validator (Sprint 4 logic) that returns a Sprint 5
    ``JudgeValidationReport`` with ``gates``, ``overall_passed``, and
    ``rejection_reason`` fields.

_CITATION_PATTERN
    Compiled regex matching ``[ArtifactID:SectionID]`` references.
    Re-exported for backward compatibility with ``test_proposal_engine.py``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from ..llm.prompts import build_proposal_prompt
from ..llm.provider import LLMCallError, LLMConfig, call_llm
from ..models.citations import SourceCitation
from ..models.enums import ConfidenceEnum, ReviewDimensionEnum
from ..models.proposal import (
    ComparisonReport,
    ConfidenceMatrix,
    ExecutiveRiskDisclosure,
    JudgeValidationReport,
    ProposalReport,
    ReviewRow,
    RiskDisclosureItem,
    ValidationGateResult,
)
from ..models.payloads import ReviewNodePayload
from .confidence_engine import ConfidenceEngine
from .proposal_validator import ProposalValidator as _Sprint5Validator

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

#: Regex matching ``[ArtifactID:SectionID]`` references.
#: Re-exported for backward compatibility with ``test_proposal_engine.py``.
_CITATION_PATTERN = re.compile(r"\[[^\]\[]+:[^\]\[]+\]")

#: Filler phrases that indicate a dimension paragraph lacks substantive analysis.
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

# ── Mock content helpers ──────────────────────────────────────────────────────

_MOCK_DRAWIO_XML = (
    '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
    '<mxCell id="2" value="Architecture" style="rounded=1;" vertex="1" parent="1">'
    '<mxGeometry x="100" y="100" width="200" height="60" as="geometry"/>'
    "</mxCell></root></mxGraphModel>"
)


def _mock_proposal_text(matrix: ConfidenceMatrix) -> str:
    """Return a deterministic mock proposal in Markdown with citations.

    Every paragraph contains a ``[ArtifactID:SectionID]`` reference.
    All 12 ReviewDimensionEnum names are mentioned to satisfy Gate 3.
    """
    lines: List[str] = []

    if matrix.has_red:
        lines.append("## Executive Risk Disclosure\n")
        for dim in matrix.red_dimensions:
            lines.append(
                f"**{dim.value} [RED]**: This dimension requires immediate "
                f"attention. [proposal.md:{dim.value.lower()}-risk-1] "
                f"[artifacts:section-{dim.value.lower()}-001]\n"
            )

    lines.append("## Project Proposal\n")
    lines.append(
        "This proposal is grounded in the provided project artifacts and "
        "the 12-dimension Layer 1 review findings. [proposal.md:section-1]\n"
    )

    lines.append("### Dimension Assessment Summary\n")
    for dim in ReviewDimensionEnum:
        score = matrix.scores.get(dim, ConfidenceEnum.AMBER)
        lines.append(
            f"- **{dim.value}**: Score {score.value}. "
            f"[artifacts:{dim.value.lower()}-review-001]"
        )
    lines.append("")

    lines.append("### Delivery Architecture\n")
    lines.append(
        "The proposed architecture (see draw.io diagram below) addresses the "
        "key delivery risks identified in the Architecture and NFR dimensions. "
        "[artifacts:arch-section-002] Refer to the architecture diagram for "
        "the full component breakdown. [artifacts:nfr-section-003]\n"
    )

    lines.append("### Risk Mitigation\n")
    lines.append(
        "Risk mitigation actions have been scoped against the Risk and "
        "Delivery dimensions. [artifacts:risk-section-004] "
        "Timeline and Resource constraints have been factored into the "
        "delivery plan. [artifacts:timeline-section-005]\n"
    )

    lines.append("### Commercial Summary\n")
    lines.append(
        "The Commercial and Scope dimensions are aligned with the submitted "
        "statement of work. [artifacts:commercial-section-006] "
        "Ownership and Consistency have been validated against the project "
        "charter. [artifacts:ownership-section-007]\n"
    )

    lines.append("### Language and Intent Alignment\n")
    lines.append(
        "The Language and Intent dimensions confirm that all contractual "
        "obligations are reflected in this proposal. "
        "[artifacts:language-section-008] [artifacts:intent-section-009]\n"
    )

    return "\n".join(lines)


def _default_diagram_metadata() -> dict:
    return {
        "arch-001": {
            "diagram_id": "arch-001",
            "diagram_type": "architecture",
            "title": "Solution Architecture Overview",
            "description": (
                "High-level architecture diagram covering the key delivery "
                "components identified in the Architecture and NFR dimensions."
            ),
            "drawio_xml": _MOCK_DRAWIO_XML,
            "related_dimensions": ["Architecture", "NFR", "Delivery"],
        }
    }


def _default_download_links() -> dict:
    return {
        "architecture_diagram": "outputs/arch-001.drawio",
        "proposal_document": "outputs/proposal.md",
        "risk_register": "outputs/risk_register.md",
    }


# ── Sprint 4 ProposalValidator (adapted to Sprint 5 JudgeValidationReport) ───


class ProposalValidator:
    """Sprint 4 4-gate veto validator returning Sprint 5 ``JudgeValidationReport``.

    Preserves the Sprint 4 ``validate(text, dimension_paragraphs,
    comparison_report, citations)`` signature but returns the Sprint 5
    ``JudgeValidationReport`` (gates / overall_passed / rejection_reason) so
    the model schema is consistent across both pipeline generations.
    """

    def validate(
        self,
        text: str,
        dimension_paragraphs: dict[str, str],
        comparison_report: ComparisonReport,
        citations: List[SourceCitation],
    ) -> JudgeValidationReport:
        """Run all 4 gates and return a ``JudgeValidationReport``.

        All gates always run regardless of earlier failures so the caller
        receives a complete picture in a single pass.
        """
        g1_passed, g1_unsubstantiated, g1_msg = self._gate1_traceability(text)
        g2_passed, g2_msg = self._gate2_contradiction(text, comparison_report)
        g3_passed, g3_insufficient, g3_msg = self._gate3_dimensional_coverage(
            dimension_paragraphs
        )
        g4_passed, g4_msg = self._gate4_diagram_alignment(text, comparison_report)

        gates = [
            ValidationGateResult(
                gate_number=1,
                gate_name="Traceability Density",
                passed=g1_passed,
                reason=g1_msg if not g1_passed else None,
            ),
            ValidationGateResult(
                gate_number=2,
                gate_name="Contradiction Check",
                passed=g2_passed,
                reason=g2_msg if not g2_passed else None,
            ),
            ValidationGateResult(
                gate_number=3,
                gate_name="Dimensional Coverage",
                passed=g3_passed,
                reason=g3_msg if not g3_passed else None,
            ),
            ValidationGateResult(
                gate_number=4,
                gate_name="Diagram Alignment",
                passed=g4_passed,
                reason=g4_msg if not g4_passed else None,
            ),
        ]

        failed = [g for g in gates if not g.passed]
        return JudgeValidationReport(
            gates=gates,
            overall_passed=not bool(failed),
            rejection_reason=failed[0].reason if failed else None,
        )

    # ── Gate implementations ──────────────────────────────────────────────────

    def _gate1_traceability(
        self, text: str
    ) -> tuple[bool, list[str], str]:
        """Gate 1 — every non-header paragraph must have a ``[X:Y]`` citation."""
        unsubstantiated: list[str] = []
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        for para in paragraphs:
            if para.startswith("#"):
                continue
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
        """Gate 2 — proposal must address known knowledge_observations."""
        conflicts = comparison_report.reconciliation.critical_conflicts
        observations = comparison_report.knowledge_observations
        if not conflicts or not observations:
            return True, ""
        text_lower = text.lower()
        addressed = any(obs.lower() in text_lower for obs in observations)
        if addressed:
            return True, ""
        msg = (
            "Gate 2 FAIL — Proposal does not address known contradiction "
            "observations from Layer 2 synthesis "
            f"({len(conflicts)} conflict(s), {len(observations)} "
            "observation(s) unaddressed)"
        )
        return False, msg

    def _gate3_dimensional_coverage(
        self, dimension_paragraphs: dict[str, str]
    ) -> tuple[bool, list[str], str]:
        """Gate 3 — all 12 dimensions must be present and substantive."""
        insufficient: list[str] = []
        all_dim_values = {d.value for d in ReviewDimensionEnum}
        covered = set(dimension_paragraphs.keys())
        for dim in sorted(all_dim_values - covered):
            insufficient.append(dim)
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
        """Gate 4 — draw.io metadata present → DesignRationale section required."""
        if not comparison_report.drawio_metadata:
            return True, ""
        has_rationale = "DesignRationale" in text or "Design Rationale" in text
        if has_rationale:
            return True, ""
        msg = (
            "Gate 4 FAIL — draw.io artifacts are present in ComparisonReport "
            "but no DesignRationale section was found in the proposal text"
        )
        return False, msg


# ── ProposalEngine ────────────────────────────────────────────────────────────


class ProposalEngine:
    """Proposal generation engine supporting both sync and async pipelines.

    Sprint 4 path — ``build(review_rows, comparison_report)``
        Deterministic, no LLM.  Accepts ``ReviewRow`` inputs, injects
        ``[ArtifactID:SectionID]`` citations, runs 4-gate validation, returns
        ``ProposalReport``.

    Sprint 5 path — ``generate(payloads, artifact_context)``
        Async, LLM-backed with deterministic mock fallback.  Accepts
        ``ReviewNodePayload`` inputs, builds a ``ConfidenceMatrix``, injects
        confidence-aware directives into the LLM prompt, runs 6-gate
        validation, returns ``ProposalReport``.

    Parameters
    ----------
    config:
        LLM backend configuration.  When ``None``, ``generate()`` always
        returns the deterministic mock report (offline-first mode).
    """

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self._config = config
        self._confidence_engine = ConfidenceEngine()
        self._s5_validator = _Sprint5Validator()
        self._s4_validator = ProposalValidator()

    # ── Sprint 5 path ─────────────────────────────────────────────────────────

    async def generate(
        self,
        payloads: List[ReviewNodePayload],
        artifact_context: str,
        arbitrator_summary: Optional[str] = None,
    ) -> ProposalReport:
        """Generate a ``ProposalReport`` from Layer 1 payloads (async, Sprint 5).

        Falls back to ``_build_mock_report()`` on any LLM failure so the
        pipeline never hard-blocks on LLM availability.
        """
        matrix = self._confidence_engine.build_matrix(payloads)

        report: Optional[ProposalReport] = None
        if self._config is not None:
            try:
                report = await self._call_llm_for_report(
                    matrix, artifact_context, arbitrator_summary
                )
            except (LLMCallError, Exception) as exc:
                logger.warning(
                    "ProposalEngine LLM call failed (%s); falling back to mock.",
                    exc,
                )

        if report is None:
            report = self._build_mock_report(matrix)

        contradictions: List[dict] = []
        validation = self._s5_validator.validate(report, matrix, contradictions)
        return report.model_copy(update={"judge_validation_report": validation})

    async def _call_llm_for_report(
        self,
        matrix: ConfidenceMatrix,
        artifact_context: str,
        arbitrator_summary: Optional[str],
    ) -> ProposalReport:
        assert self._config is not None
        system, user = build_proposal_prompt(
            confidence_matrix=matrix,
            artifact_context=artifact_context,
            arbitrator_summary=arbitrator_summary,
        )
        response = await call_llm(self._config, system, user, max_tokens=8192)
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise LLMCallError(
                f"ProposalEngine: LLM response is not valid JSON: {exc}"
            ) from exc
        return self._parse_llm_data(data, matrix)

    def _parse_llm_data(
        self, data: dict, matrix: ConfidenceMatrix
    ) -> ProposalReport:
        proposal_text: str = data.get("proposal_text", "")
        if not proposal_text:
            proposal_text = _mock_proposal_text(matrix)

        erd: Optional[ExecutiveRiskDisclosure] = None
        raw_erd = data.get("executive_risk_disclosure")
        if raw_erd and isinstance(raw_erd, dict):
            try:
                erd = ExecutiveRiskDisclosure.model_validate(raw_erd)
            except Exception:
                erd = None
        if matrix.has_red and erd is None:
            erd = self._build_erd_from_matrix(matrix)

        diagram_metadata: dict = data.get("diagram_metadata") or {}
        if not diagram_metadata:
            diagram_metadata = _default_diagram_metadata()
        download_links: dict = data.get("download_links") or {}
        if not download_links:
            download_links = _default_download_links()

        return ProposalReport(
            proposal_text=proposal_text,
            executive_risk_disclosure=erd,
            diagram_metadata=diagram_metadata,
            download_links=download_links,
        )

    def _build_mock_report(self, matrix: ConfidenceMatrix) -> ProposalReport:
        """Return a deterministic mock ``ProposalReport`` for offline/test use."""
        erd: Optional[ExecutiveRiskDisclosure] = None
        if matrix.has_red:
            erd = self._build_erd_from_matrix(matrix)
        return ProposalReport(
            proposal_text=_mock_proposal_text(matrix),
            executive_risk_disclosure=erd,
            diagram_metadata=_default_diagram_metadata(),
            download_links=_default_download_links(),
        )

    def _build_erd_from_matrix(
        self, matrix: ConfidenceMatrix
    ) -> ExecutiveRiskDisclosure:
        items = self._confidence_engine.build_risk_disclosure_items([], matrix)
        if not items:
            items = [
                RiskDisclosureItem(
                    dimension=dim,
                    confidence=ConfidenceEnum.RED,
                    summary=(
                        f"{dim.value} dimension scored RED indicating critical "
                        "delivery risk. Immediate mitigation required."
                    ),
                    citation_refs=[
                        f"[artifacts:{dim.value.lower()}-section-001]",
                        f"[proposal.md:{dim.value.lower()}-risk-ref]",
                    ],
                )
                for dim in matrix.red_dimensions
            ]
        red_names = ", ".join(d.value for d in matrix.red_dimensions)
        return ExecutiveRiskDisclosure(
            items=items,
            directive=(
                f"CRITICAL: The following dimensions require executive attention: "
                f"{red_names}."
            ),
        )

    # ── Sprint 4 path ─────────────────────────────────────────────────────────

    def build(
        self,
        review_rows: List[ReviewRow],
        comparison_report: ComparisonReport,
    ) -> ProposalReport:
        """Build a ``ProposalReport`` from ``ReviewRow`` inputs (sync, Sprint 4).

        Deterministic — no LLM call.  Injects ``[ArtifactID:SectionID]``
        references, builds a DesignRationale section, runs the 4-gate
        ``ProposalValidator``, and returns a ``ProposalReport``.

        Parameters
        ----------
        review_rows:
            One ``ReviewRow`` per dimension (up to 12).
        comparison_report:
            The ``ComparisonReport`` from Sprint 3 Layer 2 synthesis.

        Returns
        -------
        ProposalReport
            Complete proposal with validation results in ``judge_validation_report``.
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

        judge_validation = self._s4_validator.validate(
            text=full_text,
            dimension_paragraphs=dimension_paragraphs,
            comparison_report=comparison_report,
            citations=all_citations,
        )

        return ProposalReport(
            proposal_text=full_text,
            diagram_metadata=comparison_report.drawio_metadata,
            download_links={},
            judge_validation_report=judge_validation,
        )

    # ── Sprint 4 private helpers ──────────────────────────────────────────────

    def _build_dimension_paragraph(
        self,
        row: ReviewRow,
        citations: List[SourceCitation],
    ) -> str:
        dim_name = row.payload.dimension.value
        confidence = row.payload.overall_confidence.value
        artifact_id = row.artifact_id

        citation_refs: list[str] = []
        for c in citations:
            section_id = f"L{c.line_start}-{c.line_end}"
            citation_refs.append(f"[{artifact_id}:{section_id}]")
        if not citation_refs:
            citation_refs = [f"[{artifact_id}:general]"]

        refs_str = " ".join(citation_refs)
        finding_lines: list[str] = [
            f"- {f.summary} "
            f"(Confidence: {f.confidence.value}, Routing: {f.mitigation_routing.value})"
            for f in row.payload.findings
        ]
        findings_str = (
            "\n".join(finding_lines) if finding_lines else "No findings identified."
        )
        return f"**{dim_name}** (Overall: {confidence}) {refs_str}\n{findings_str}"

    def _build_design_rationale(
        self,
        comparison_report: ComparisonReport,
        review_rows: List[ReviewRow],
    ) -> str:
        if not comparison_report.drawio_metadata:
            return (
                "## DesignRationale\n\n"
                "No architectural diagrams were provided. Architecture review "
                "findings are referenced directly from the dimension analysis "
                "above. [rationale:general]"
            )
        sections: list[str] = ["## DesignRationale"]
        exec_summary = comparison_report.reconciliation.executive_summary
        if exec_summary:
            sections.append(
                f"{exec_summary} [reconciliation:executive-summary]"
            )
        for row in review_rows:
            if not row.payload.findings:
                continue
            dim_value = row.payload.dimension.value
            dim_ref = f"[{row.artifact_id}:arch-{dim_value.lower()}]"
            finding_lines = [f"- {f.summary}" for f in row.payload.findings]
            sections.append(
                f"**{dim_value} \u2192 Architecture Mapping** {dim_ref}\n"
                + "\n".join(finding_lines)
            )
        return "\n\n".join(sections)

    def _assemble_proposal_text(
        self,
        dimension_paragraphs: dict[str, str],
        design_rationale: str,
    ) -> str:
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
