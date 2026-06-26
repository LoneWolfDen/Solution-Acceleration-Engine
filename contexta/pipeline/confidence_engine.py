"""ConfidenceEngine — Sprint 5.

Builds a ``ConfidenceMatrix`` from the 12 completed ``ReviewNodePayload``
objects produced by Layer 1.  The matrix drives the mandatory Executive Risk
Disclosure logic in ``ProposalEngine``.

Design contracts
----------------
- ``build_matrix()`` maps each payload's ``dimension`` to its
  ``overall_confidence``.  Missing dimensions produce no entry; callers
  should pass all 12 payloads for a complete matrix.
- ``get_red_summaries()`` returns the first finding summary per RED dimension,
  giving the ProposalEngine concrete risk text to embed in the prompt.
- ``get_red_citations()`` formats ``SourceCitation`` objects into
  ``[ArtifactID:SectionID]`` strings for the Executive Risk Disclosure.
"""

from __future__ import annotations

from typing import Dict, List

from ..models.enums import ConfidenceEnum, ReviewDimensionEnum
from ..models.payloads import ReviewNodePayload
from ..models.proposal import ConfidenceMatrix, RiskDisclosureItem


class ConfidenceEngine:
    """Builds confidence scoring artefacts from Layer 1 review payloads."""

    def build_matrix(self, payloads: List[ReviewNodePayload]) -> ConfidenceMatrix:
        """Build a ``ConfidenceMatrix`` from completed dimension payloads.

        Parameters
        ----------
        payloads:
            ``ReviewNodePayload`` objects — typically all 12 Layer 1 results.
            Duplicate dimensions are last-write-wins.

        Returns
        -------
        ConfidenceMatrix
            Fully populated matrix with bucketed dimension lists and the
            ``has_red`` convenience flag.
        """
        scores: Dict[ReviewDimensionEnum, ConfidenceEnum] = {}
        for payload in payloads:
            scores[payload.dimension] = payload.overall_confidence

        red = [d for d, c in scores.items() if c == ConfidenceEnum.RED]
        amber = [d for d, c in scores.items() if c == ConfidenceEnum.AMBER]
        green = [d for d, c in scores.items() if c == ConfidenceEnum.GREEN]

        return ConfidenceMatrix(
            scores=scores,
            red_dimensions=red,
            amber_dimensions=amber,
            green_dimensions=green,
            has_red=bool(red),
        )

    def get_red_summaries(
        self,
        payloads: List[ReviewNodePayload],
        matrix: ConfidenceMatrix,
    ) -> Dict[ReviewDimensionEnum, str]:
        """Return the first finding summary for each RED-scored dimension.

        Parameters
        ----------
        payloads:
            Original Layer 1 payloads used to build *matrix*.
        matrix:
            ``ConfidenceMatrix`` produced by ``build_matrix()``.

        Returns
        -------
        Dict[ReviewDimensionEnum, str]
            Mapping of RED dimension → first finding summary string.
            Dimensions with no findings map to an empty string.
        """
        summaries: Dict[ReviewDimensionEnum, str] = {}
        for payload in payloads:
            if payload.dimension in matrix.red_dimensions:
                if payload.findings:
                    summaries[payload.dimension] = payload.findings[0].summary
                else:
                    summaries[payload.dimension] = ""
        return summaries

    def get_red_citations(
        self,
        payloads: List[ReviewNodePayload],
        matrix: ConfidenceMatrix,
    ) -> Dict[ReviewDimensionEnum, List[str]]:
        """Return formatted citation refs for each RED-scored dimension.

        Citations are formatted as ``[<file_path>:<line_start>-<line_end>]``
        strings derived from ``SourceCitation`` objects on each finding.

        Parameters
        ----------
        payloads:
            Original Layer 1 payloads used to build *matrix*.
        matrix:
            ``ConfidenceMatrix`` produced by ``build_matrix()``.

        Returns
        -------
        Dict[ReviewDimensionEnum, List[str]]
            Mapping of RED dimension → list of citation ref strings.
            Dimensions with no citations return an empty list.
        """
        citations: Dict[ReviewDimensionEnum, List[str]] = {}
        for payload in payloads:
            if payload.dimension not in matrix.red_dimensions:
                continue
            refs: List[str] = []
            for finding in payload.findings:
                for citation in finding.citations:
                    ref = (
                        f"[{citation.file_path}:"
                        f"{citation.line_start}-{citation.line_end}]"
                    )
                    refs.append(ref)
            citations[payload.dimension] = refs
        return citations

    def build_risk_disclosure_items(
        self,
        payloads: List[ReviewNodePayload],
        matrix: ConfidenceMatrix,
    ) -> List[RiskDisclosureItem]:
        """Build ``RiskDisclosureItem`` objects for all RED dimensions.

        Combines ``get_red_summaries()`` and ``get_red_citations()`` into
        the typed objects used by ``ExecutiveRiskDisclosure``.

        Parameters
        ----------
        payloads:
            Original Layer 1 payloads.
        matrix:
            ``ConfidenceMatrix`` with at least one RED dimension.

        Returns
        -------
        List[RiskDisclosureItem]
            One item per RED dimension; empty list when ``matrix.has_red``
            is ``False``.
        """
        if not matrix.has_red:
            return []

        summaries = self.get_red_summaries(payloads, matrix)
        citations = self.get_red_citations(payloads, matrix)

        items: List[RiskDisclosureItem] = []
        for dim in matrix.red_dimensions:
            items.append(
                RiskDisclosureItem(
                    dimension=dim,
                    confidence=ConfidenceEnum.RED,
                    summary=summaries.get(dim, f"{dim.value} dimension scored RED."),
                    citation_refs=citations.get(dim, []),
                )
            )
        return items
