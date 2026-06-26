"""The Learning Loop — Sprint 6: PromptOptimizer service.

Three cooperating classes implement the learning loop:

PromptOptimizer
    Reads Layer 1 exploration NodeRows and extracts [ArtifactID:SectionID]
    citation usage trends.  ArtifactID = file_path; SectionID = line_start-line_end.
    Writes CITATION_TREND records to the intelligence_layer table.

KnowledgeAggregator
    Computes a ConfidenceMatrix keyed by version_id, scoped per-project.
    Trend analysis shows how each dimension's confidence changed across versions.
    Writes CONFIDENCE_TREND records to the intelligence_layer table.

PromptDelta
    Compares JudgeValidationReport gate failures against the active BasePersona
    prompt and emits a JSON delta of recommended prompt adjustments.  One
    suggestion per failed gate — deterministic mapping, no LLM call required.
    Writes PROMPT_DELTA records to the intelligence_layer table.

Design constraints
------------------
- All three classes are read-only against existing tables (projects, versions,
  nodes, prompt_blueprints).  The only writes they perform target the new
  intelligence_layer table via the repository functions in db/repositories.py.
- No UI changes.  All public methods return typed Pydantic models that callers
  can inspect, log, or persist independently.
- Deterministic: given the same input data, every method returns the same result.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Dict, List, Optional

import aiosqlite
from pydantic import BaseModel

from ..db.models import BlueprintRow, IntelligenceRow, NodeRow
from ..llm.models import (
    GateNameEnum,
    JudgeValidationReport,
    evaluate_reconciliation_report,
)
from ..models.enums import ReviewDimensionEnum
from ..models.payloads import ReviewNodePayload

logger = logging.getLogger(__name__)


# ── Insight type constants ─────────────────────────────────────────────────────

INSIGHT_TYPE_CITATION_TREND: str = "CITATION_TREND"
INSIGHT_TYPE_CONFIDENCE_TREND: str = "CONFIDENCE_TREND"
INSIGHT_TYPE_PROMPT_DELTA: str = "PROMPT_DELTA"


# ── Result models ──────────────────────────────────────────────────────────────


class CitationTrend(BaseModel):
    """Usage frequency for a specific [ArtifactID:SectionID] citation span.

    ArtifactID maps to ``SourceCitation.file_path``.
    SectionID  maps to ``f"{line_start}-{line_end}"``.

    Attributes:
        artifact_id: Source file path as recorded by ArtifactRegistry.
        section_id:  Line range string: "<line_start>-<line_end>".
        frequency:   Number of times this span was cited across all findings
                     in the analysed exploration nodes.
    """

    artifact_id: str
    section_id: str
    frequency: int


class ConfidenceMatrix(BaseModel):
    """Per-version snapshot of all dimension confidence scores for one project.

    Enables trend analysis: did the Timeline dimension improve
    RED → AMBER → GREEN across v1, v2, v3?

    Attributes:
        project_id:    The project this matrix is scoped to.
        version_order: version_ids ordered by created_at (oldest first).
        matrix:        Nested mapping ``{version_id: {dimension_value: confidence_value}}``.
                       Only dimensions that produced findings are included — dimensions
                       absent from a version are omitted rather than defaulted.
    """

    project_id: str
    version_order: List[str]
    matrix: Dict[str, Dict[str, str]]


class PromptDeltaResult(BaseModel):
    """Recommended prompt adjustments derived from JudgeValidationReport gate failures.

    Attributes:
        gate_failures:           gate_name values of every gate that did not pass.
        delta_json:              Mapping from adjustment_key → suggested_addition text.
                                 One entry per failed gate.
        base_prompt_length:      Character count of the active blueprint prompt.
        applied_to_blueprint_id: id of the BlueprintRow the delta was generated against.
    """

    gate_failures: List[str]
    delta_json: Dict[str, str]
    base_prompt_length: int
    applied_to_blueprint_id: str


# ── Gate → prompt adjustment mapping ──────────────────────────────────────────

#: Deterministic mapping from GateNameEnum value → (adjustment_key, suggested_text).
#: Used by PromptDelta.generate() to build the delta_json payload.
_GATE_DELTA_MAP: Dict[str, tuple[str, str]] = {
    GateNameEnum.APPROVAL_GATE: (
        "approval_gate_guidance",
        (
            "Ensure all identified issues have clear mitigations documented before "
            "recommending non-approval. If blockers cannot be resolved, state them "
            "explicitly with escalation paths."
        ),
    ),
    GateNameEnum.DELIVERY_CONFIDENCE: (
        "confidence_calibration",
        (
            "Calibrate your confidence assessment against industry delivery benchmarks. "
            "The score must reflect both identified risks AND the strength of proposed "
            "mitigations — a low score requires explicit justification."
        ),
    ),
    GateNameEnum.CONFLICT_SEVERITY_CONTROL: (
        "critical_conflict_resolution",
        (
            "For every Critical-severity conflict identified, provide a concrete path "
            "to resolution before assigning Critical severity. Reserve 'Critical' for "
            "conflicts that are genuinely unresolvable within the current proposal scope."
        ),
    ),
    GateNameEnum.CONFLICT_COUNT_BOUNDED: (
        "conflict_consolidation",
        (
            "Focus on the top 3 most impactful cross-dimension conflicts. Consolidate "
            "minor friction points under broader thematic conflicts rather than listing "
            "each individually."
        ),
    ),
    GateNameEnum.RECOMMENDATIONS_PRESENT: (
        "recommendations_mandatory",
        (
            "Always conclude with at least one actionable recommendation, even for "
            "structurally sound proposals. Recommendations must be sequential and "
            "specific enough for the delivery lead to act on immediately."
        ),
    ),
    GateNameEnum.EXECUTIVE_SUMMARY_SUBSTANTIVE: (
        "executive_summary_depth",
        (
            "The executive summary must provide a substantive synthesis of overall "
            "project viability — minimum 50 characters. Avoid generic statements; "
            "reference the specific dimensions and conflicts that drove your assessment."
        ),
    ),
}


# ── PromptOptimizer ────────────────────────────────────────────────────────────


class PromptOptimizer:
    """Extracts [ArtifactID:SectionID] citation usage trends from exploration NodeRows.

    Reads the ``metadata_json['dimensions']`` payload written by
    ``commit_exploration_node()`` and tallies how frequently each
    ``(file_path, line_start-line_end)`` span was cited across all findings.

    Parameters
    ----------
    conn:
        Open aiosqlite connection.  Used for DB persistence; extraction
        methods that accept in-memory data do not require a connection.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # ── Public ─────────────────────────────────────────────────────────────────

    def extract_citation_trends(
        self, nodes: List[NodeRow]
    ) -> List[CitationTrend]:
        """Extract [ArtifactID:SectionID] citation frequencies from a list of NodeRows.

        Only exploration-layer nodes are processed; synthesis nodes are skipped
        because their ``metadata_json`` does not contain a ``'dimensions'`` key.

        Parameters
        ----------
        nodes:
            List of ``NodeRow`` objects.  Typically retrieved via
            ``list_nodes_for_project()`` filtered to ``layer_type='exploration'``.

        Returns
        -------
        List[CitationTrend]
            Sorted descending by frequency, then ascending by artifact_id,
            then ascending by section_id.  Empty list if no citations found.
        """
        counter: Counter[tuple[str, str]] = Counter()

        for node in nodes:
            if node.layer_type != "exploration":
                continue
            dimensions_data = self._extract_dimensions(node)
            for dim_dict in dimensions_data:
                for finding in dim_dict.get("findings", []):
                    for citation in finding.get("citations", []):
                        file_path = citation.get("file_path", "")
                        line_start = citation.get("line_start")
                        line_end = citation.get("line_end")
                        if file_path and line_start is not None and line_end is not None:
                            counter[(file_path, f"{line_start}-{line_end}")] += 1

        return sorted(
            [
                CitationTrend(
                    artifact_id=artifact_id,
                    section_id=section_id,
                    frequency=freq,
                )
                for (artifact_id, section_id), freq in counter.items()
            ],
            key=lambda t: (-t.frequency, t.artifact_id, t.section_id),
        )

    async def run_for_project(
        self,
        project_id: str,
        source_node_id: Optional[str] = None,
    ) -> IntelligenceRow:
        """Run citation trend extraction for a project and persist the result.

        Loads all nodes for *project_id*, extracts citation trends, serialises
        to JSON, and writes a CITATION_TREND record to ``intelligence_layer``.

        Parameters
        ----------
        project_id:
            The project to analyse.
        source_node_id:
            Optional FK to the primary exploration node this run is derived from.

        Returns
        -------
        IntelligenceRow
            The persisted intelligence record.
        """
        from ..db.repositories import list_nodes_for_project, write_intelligence_record

        nodes = await list_nodes_for_project(self._conn, project_id)
        trends = self.extract_citation_trends(nodes)
        payload = {"trends": [t.model_dump() for t in trends]}

        return await write_intelligence_record(
            self._conn,
            insight_type=INSIGHT_TYPE_CITATION_TREND,
            payload=payload,
            project_id=project_id,
            source_node_id=source_node_id,
        )

    # ── Internal ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_dimensions(node: NodeRow) -> List[dict]:
        """Parse ``metadata_json['dimensions']`` from a NodeRow.

        Returns an empty list if the key is absent or the JSON is malformed.
        Never raises — parse failures are logged and skipped.
        """
        raw = node.metadata_json
        try:
            meta: dict = json.loads(raw) if isinstance(raw, str) else raw
            dims = meta.get("dimensions", [])
            return dims if isinstance(dims, list) else []
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.debug("Skipping node %s: metadata_json parse error: %s", node.id, exc)
            return []


# ── KnowledgeAggregator ────────────────────────────────────────────────────────


class KnowledgeAggregator:
    """Computes a ConfidenceMatrix across all versions of a project.

    For each version, the aggregator loads all exploration nodes assigned to
    that version (``nodes.version_id = versions.id``) and records the
    ``overall_confidence`` for every dimension.  The resulting matrix enables
    trend analysis: did Timeline improve RED → AMBER → GREEN across v1/v2/v3?

    Parameters
    ----------
    conn:
        Open aiosqlite connection.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # ── Public ─────────────────────────────────────────────────────────────────

    async def compute_confidence_matrix(
        self, project_id: str
    ) -> ConfidenceMatrix:
        """Build a ConfidenceMatrix for *project_id* across all its versions.

        Versions with no exploration nodes are included in ``version_order``
        but have an empty dict in ``matrix`` — this preserves the full
        chronological timeline even for incomplete versions.

        Parameters
        ----------
        project_id:
            The project to aggregate.

        Returns
        -------
        ConfidenceMatrix
            Versions ordered oldest-first; matrix keyed by version_id.
        """
        from ..db.repositories import list_nodes_for_project, list_versions_for_project

        versions = await list_versions_for_project(self._conn, project_id)
        all_nodes = await list_nodes_for_project(self._conn, project_id)

        # Index exploration nodes by version_id for O(1) lookup.
        nodes_by_version: Dict[str, List[NodeRow]] = {}
        for node in all_nodes:
            if node.layer_type == "exploration" and node.version_id:
                nodes_by_version.setdefault(node.version_id, []).append(node)

        version_order = [v.id for v in versions]
        matrix: Dict[str, Dict[str, str]] = {}

        for version in versions:
            version_nodes = nodes_by_version.get(version.id, [])
            dim_confidence: Dict[str, str] = {}
            for node in version_nodes:
                dim_confidence.update(self._extract_dimension_confidences(node))
            matrix[version.id] = dim_confidence

        return ConfidenceMatrix(
            project_id=project_id,
            version_order=version_order,
            matrix=matrix,
        )

    async def run_for_project(self, project_id: str) -> IntelligenceRow:
        """Compute and persist the ConfidenceMatrix for *project_id*.

        Writes a CONFIDENCE_TREND record to ``intelligence_layer``.

        Parameters
        ----------
        project_id:
            The project to aggregate.

        Returns
        -------
        IntelligenceRow
            The persisted intelligence record.
        """
        from ..db.repositories import write_intelligence_record

        matrix = await self.compute_confidence_matrix(project_id)
        payload = matrix.model_dump()

        return await write_intelligence_record(
            self._conn,
            insight_type=INSIGHT_TYPE_CONFIDENCE_TREND,
            payload=payload,
            project_id=project_id,
        )

    # ── Internal ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_dimension_confidences(node: NodeRow) -> Dict[str, str]:
        """Extract ``{dimension_value: overall_confidence}`` from an exploration node.

        Reads ``metadata_json['dimensions']`` and returns one entry per
        dimension that has a valid ``overall_confidence`` field.

        Returns an empty dict on parse failure — never raises.
        """
        raw = node.metadata_json
        try:
            meta: dict = json.loads(raw) if isinstance(raw, str) else raw
            dims: list = meta.get("dimensions", [])
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.debug(
                "Skipping node %s: metadata_json parse error: %s", node.id, exc
            )
            return {}

        result: Dict[str, str] = {}
        for dim_dict in dims:
            dimension = dim_dict.get("dimension")
            confidence = dim_dict.get("overall_confidence")
            if dimension and confidence:
                result[dimension] = confidence
        return result


# ── PromptDelta ────────────────────────────────────────────────────────────────


class PromptDelta:
    """Compares JudgeValidationReport gate failures against the active prompt.

    For each failed gate, a deterministic, pre-mapped adjustment suggestion is
    produced.  No LLM call is made — the mapping in ``_GATE_DELTA_MAP`` is the
    authoritative source of truth for prompt adjustment guidance.

    Parameters
    ----------
    conn:
        Open aiosqlite connection.  Used for DB persistence only.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # ── Public ─────────────────────────────────────────────────────────────────

    def generate(
        self,
        judge_report: JudgeValidationReport,
        blueprint: BlueprintRow,
    ) -> PromptDeltaResult:
        """Generate a prompt delta from gate failures.

        Iterates over all failed gates in *judge_report*, looks up the
        deterministic adjustment text from ``_GATE_DELTA_MAP``, and assembles
        a ``PromptDeltaResult``.  Gates that passed produce no output.

        Parameters
        ----------
        judge_report:
            The JudgeValidationReport to analyse.
        blueprint:
            The currently active BlueprintRow whose ``master_prompt_text``
            is the baseline being adjusted.

        Returns
        -------
        PromptDeltaResult
            Contains delta_json with one entry per failed gate.
            If all gates passed, gate_failures and delta_json are empty.
        """
        gate_failures: List[str] = []
        delta_json: Dict[str, str] = {}

        for gate_check in judge_report.gate_checks:
            if not gate_check.passed:
                gate_name = gate_check.gate_name
                gate_failures.append(gate_name)
                if gate_name in _GATE_DELTA_MAP:
                    adjustment_key, suggested_text = _GATE_DELTA_MAP[gate_name]
                    delta_json[adjustment_key] = suggested_text
                else:
                    logger.warning(
                        "No delta mapping found for gate %r — skipping.", gate_name
                    )

        return PromptDeltaResult(
            gate_failures=gate_failures,
            delta_json=delta_json,
            base_prompt_length=len(blueprint.master_prompt_text),
            applied_to_blueprint_id=blueprint.id,
        )

    async def run(
        self,
        judge_report: JudgeValidationReport,
        blueprint: BlueprintRow,
        project_id: Optional[str] = None,
        source_node_id: Optional[str] = None,
    ) -> IntelligenceRow:
        """Generate a prompt delta and persist it to intelligence_layer.

        Parameters
        ----------
        judge_report:
            The JudgeValidationReport to analyse.
        blueprint:
            The active BlueprintRow being evaluated.
        project_id:
            Optional project scope.  None = global prompt delta.
        source_node_id:
            Optional FK to the synthesis node this report was derived from.

        Returns
        -------
        IntelligenceRow
            The persisted PROMPT_DELTA intelligence record.
        """
        from ..db.repositories import write_intelligence_record

        result = self.generate(judge_report, blueprint)
        payload = result.model_dump()

        return await write_intelligence_record(
            self._conn,
            insight_type=INSIGHT_TYPE_PROMPT_DELTA,
            payload=payload,
            project_id=project_id,
            source_node_id=source_node_id,
        )
