"""Layer 2 Synthesis — Arbitrator Engine.

The ``ArbitratorEngine`` takes all 12 completed ``ReviewNodePayload`` objects,
runs a single LLM call via the Arbitrator Persona, and returns an
``ArbitratorResult`` containing detected contradictions.

Sprint 2 additions
------------------
``ReviewContext``, ``ProvenanceEntry``, ``TracedArbitratorOutput``, and
``ArbitratorEngine.run_with_context()`` implement the mock orchestration path
required by Sprint 2.  The mock runs deterministically — no LLM call — and
produces output that satisfies the Traceability Standard (scope.md §3):

  - Every cited finding is mapped 1:1 to ``[ArtifactID:SectionID]``.
  - Unsubstantiated findings (no ``SourceCitation``) are flagged explicitly.
  - Traceability density is calculated as cited / total findings.
  - The full output is serialisable to JSON via ``TracedArbitratorOutput.to_json()``.

Design contracts
----------------
- ``run()`` raises ``ArbitratorError`` immediately if ``len(payloads) != 12``,
  before any LLM call is made (Property 13).
- ``run_with_context()`` raises ``ArbitratorError`` if ``len(payloads) != 12``
  OR if ``context.version_id`` is empty — both checked before any processing.
- Temperature-Zero Mode is enforced by ``call_llm()`` — the engine does not
  need to set temperature itself.
The ``LayerTwoArbitrator`` performs the full Layer 2 synthesis call, producing
a validated ``ReconciliationReport``.

Both engines optionally accept a ``KnowledgeContext`` so that prior user
interventions stored in KnowledgeMemory can be injected as Contextual
Constraints to guide contradiction detection and synthesis.

Design contracts
----------------
- ``ArbitratorEngine.run()`` raises ``ArbitratorError`` immediately if
  ``len(payloads) != 12``, before any LLM call is made (Property 13).
- Temperature-Zero Mode is enforced by ``call_llm()`` — the engines do not
  need to set temperature themselves.
- JSON parsing failures raise ``ArbitratorError``, not bare ``JSONDecodeError``.
- ``knowledge_service`` is optional in both engines; callers that have not
  wired KnowledgeMemory simply omit it and behaviour is unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING, Awaitable, Callable, List, Optional
from enum import Enum

from ..llm.provider import LLMConfig, call_llm
from ..llm.prompts import PromptBuilder
from ..models.payloads import ReviewNodePayload

if TYPE_CHECKING:
    from ..knowledge.memory import KnowledgeContext, KnowledgeMemoryService


# ── Status enum ───────────────────────────────────────────────────────────────


class ArbitrationStatus(str, Enum):
    """Lifecycle states emitted by ``ArbitratorEngine.run()`` via its callback."""

    PROCESSING = "PROCESSING"
    RATE_LIMITED = "RATE_LIMITED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


# ── Exception ─────────────────────────────────────────────────────────────────


class ArbitratorError(Exception):
    """Raised when the Arbitrator call fails or its response cannot be parsed."""


# ── Result ────────────────────────────────────────────────────────────────────


@dataclass
class ArbitratorResult:
    """Structured output of the Layer 2 Arbitrator synthesis."""

    contradictions: List[dict]
    raw_llm_response: str


# ── Engine ────────────────────────────────────────────────────────────────────


class ArbitratorEngine:
    """Runs the Layer 2 synthesis LLM call.

    Parameters
    ----------
    config:
        LLM backend configuration passed through to ``call_llm()``.
    builder:
        ``PromptBuilder`` instance (uses the active blueprint).
    knowledge_service:
        Optional ``KnowledgeMemoryService``.  When provided, observations
        matching the supplied ``KnowledgeContext`` are fetched before the LLM
        call and injected as Contextual Constraints into the system prompt.
    """

    def __init__(
        self,
        config: LLMConfig,
        builder: PromptBuilder,
        knowledge_service: Optional["KnowledgeMemoryService"] = None,
    ) -> None:
        self._config = config
        self._builder = builder
        self._knowledge_service = knowledge_service

    async def run(
        self,
        payloads: List[ReviewNodePayload],
        context: Optional["KnowledgeContext"] = None,
        callback: Optional[Callable[[ArbitrationStatus, str], Awaitable[None]]] = None,
    ) -> ArbitratorResult:
        """Execute the Arbitrator synthesis.

        Parameters
        ----------
        payloads:
            Exactly 12 validated ``ReviewNodePayload`` objects — one per
            ``ReviewDimensionEnum`` value.
        context:
            Optional ``KnowledgeContext`` used to fetch prior observations from
            KnowledgeMemory.  Ignored when ``knowledge_service`` is ``None``.
        callback:
            Optional async callable invoked at each status transition.
            Receives ``(ArbitrationStatus, detail_string)``.  Exceptions raised
            inside the callback are silently suppressed so they never abort
            the pipeline.

        Returns
        -------
        ArbitratorResult
            Contradictions list and the raw LLM response string.

        Raises
        ------
        ArbitratorError
            If ``len(payloads) != 12``, if the LLM call fails, or if the
            response JSON cannot be parsed.
        """

        async def _emit(status: ArbitrationStatus, detail: str) -> None:
            if callback is not None:
                try:
                    await callback(status, detail)
                except Exception:
                    pass

        await _emit(ArbitrationStatus.PROCESSING, "Validating payload count")

        if len(payloads) != 12:
            msg = f"Arbitrator requires exactly 12 payloads, got {len(payloads)}"
            await _emit(ArbitrationStatus.FAILED, msg)
            raise ArbitratorError(msg)

        observations = []
        if self._knowledge_service is not None and context is not None:
            observations = await self._knowledge_service.get_observations(context)

        serialised = [p.model_dump_json() for p in payloads]
        system, user = self._builder.build_arbitrator_prompt(serialised, observations)

        await _emit(ArbitrationStatus.PROCESSING, "Calling arbitrator LLM")

        try:
            response = await call_llm(self._config, system, user)
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "rate" in exc_str.lower():
                await _emit(ArbitrationStatus.RATE_LIMITED, "Rate limit encountered")
            else:
                await _emit(ArbitrationStatus.FAILED, f"LLM call failed: {exc_str}")
            raise ArbitratorError(f"Arbitrator LLM call failed: {exc}") from exc

        await _emit(ArbitrationStatus.PROCESSING, "Parsing arbitrator response")

        try:
            data = json.loads(response.content)
            contradictions: List[dict] = data.get("contradictions", [])
        except (json.JSONDecodeError, AttributeError) as exc:
            msg = f"Arbitrator response parsing failed: {exc}"
            await _emit(ArbitrationStatus.FAILED, msg)
            raise ArbitratorError(msg) from exc

        await _emit(
            ArbitrationStatus.COMPLETE,
            f"{len(contradictions)} contradiction(s) found",
        )

        return ArbitratorResult(
            contradictions=contradictions,
            raw_llm_response=response.content,
        )



# ── Layer 2 Synthesis ─────────────────────────────────────────────────────────


class LayerTwoArbitratorError(Exception):
    """Raised when the Layer 2 synthesis LLM call fails or its response cannot
    be validated against ``ReconciliationReport``."""


class LayerTwoArbitrator:
    """Runs the Layer 2 synthesis pipeline.

    Accepts the aggregated ``IssueFinding`` objects from all 12 Layer 1
    dimensions, issues a single LLM synthesis call, and returns a validated
    ``ReconciliationReport``.

    When a ``KnowledgeMemoryService`` is provided, prior user interventions
    are fetched and injected as Contextual Constraints into the synthesis
    prompt so that the engine learns from accumulated manual corrections.

    The ``_normalise_json_content`` array-unwrapping fix in ``call_llm()``
    is applied automatically — no additional handling is needed here.

    Parameters
    ----------
    config:
        Application-level ``ContextaConfig`` — model identity and credentials
        are derived from it directly so callers do not need to construct a
        separate ``LLMConfig``.
    knowledge_service:
        Optional ``KnowledgeMemoryService``.  When provided, observations are
        fetched before synthesis and injected into the system prompt.
    """

    def __init__(
        self,
        config: "ContextaConfig",  # type: ignore[name-defined]
        knowledge_service: Optional["KnowledgeMemoryService"] = None,
    ) -> None:
        from ..config import ContextaConfig  # local import avoids top-level cycle
        from ..llm.provider import LLMConfig

        self._config = config
        self._llm_config = LLMConfig(
            model=config.llm_backend,
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
        )
        self._knowledge_service = knowledge_service

    def _build_synthesis_prompt(
        self,
        findings: List,
        observations: Optional[list] = None,
    ) -> "tuple[str, str]":
        """Delegate prompt construction to ``build_synthesis_prompt``.

        Passes *observations* through so that Contextual Constraints are
        injected when KnowledgeMemory has prior interventions available.

        Returns
        -------
        tuple[str, str]
            ``(system_prompt, user_prompt)`` ready for ``call_llm()``.
        """
        from ..llm.prompts import build_synthesis_prompt

        return build_synthesis_prompt(findings, observations or [])

    async def synthesize(
        self,
        findings: List,
        context: Optional["KnowledgeContext"] = None,
    ) -> "ReconciliationReport":  # type: ignore[name-defined]
        """Execute the Layer 2 synthesis.

        Parameters
        ----------
        findings:
            ``IssueFinding`` objects collected from all completed Layer 1
            dimension payloads.  An empty list is accepted — the LLM will
            produce a minimal report reflecting no identified issues.
        context:
            Optional ``KnowledgeContext`` used to fetch prior observations.
            Ignored when ``knowledge_service`` is ``None``.

        Returns
        -------
        ReconciliationReport
            Validated synthesis output.

        Raises
        ------
        LayerTwoArbitratorError
            If the LLM call fails or the response cannot be validated.
        """
        from ..llm.models import ReconciliationReport
        from pydantic import ValidationError

        observations = []
        if self._knowledge_service is not None and context is not None:
            observations = await self._knowledge_service.get_observations(context)

        system, user = self._build_synthesis_prompt(findings, observations)

        try:
            response = await call_llm(self._llm_config, system, user)
        except Exception as exc:
            raise LayerTwoArbitratorError(
                f"Layer 2 synthesis LLM call failed: {exc}"
            ) from exc

        try:
            report = ReconciliationReport.model_validate_json(response.content)
        except (ValidationError, ValueError) as exc:
            raise LayerTwoArbitratorError(
                f"Layer 2 synthesis response validation failed: {exc}"
            ) from exc

        return report



# ── Sprint 2: Review Engine Orchestration ────────────────────────────────────


@dataclass
class ReviewContext:
    """Input context for ``ArbitratorEngine.run_with_context()``.

    Carries the fields sourced from a ``ReviewRow`` that provide the persona,
    user briefing, and SME augmentations for a single arbitration run.

    Attributes:
        version_id:            Provenance anchor — FK → versions.id.  Must be
                               non-empty; ``ArbitratorError`` is raised if blank.
        persona_prompt:        The persona prompt that frames this review.
        user_context_text:     Free-text user-supplied context or briefing.
        sme_augmentation_list: List of SME knowledge augmentation strings
                               applied to the review run.  May be empty.
    """

    version_id:            str
    persona_prompt:        str
    user_context_text:     str
    sme_augmentation_list: List[str] = field(default_factory=list)


@dataclass
class ProvenanceEntry:
    """Maps one ``IssueFinding`` to its canonical ``[ArtifactID:SectionID]`` ref.

    Satisfies the Traceability Standard (scope.md §3): all AI outputs must
    map 1:1 to ``[ArtifactID:SectionID]``.

    The ``artifact_ref`` format is ``[<file_path>:<line_start>-<line_end>]``,
    e.g. ``[/proposal.md:1-5]``.

    Attributes:
        artifact_ref:    Canonical citation reference.
        dimension:       ``ReviewDimensionEnum`` value string.
        confidence:      ``ConfidenceEnum`` value string for this finding.
        finding_summary: Human-readable summary from ``IssueFinding.summary``.
        citation_type:   ``CitationTypeEnum`` value string.
    """

    artifact_ref:    str
    dimension:       str
    confidence:      str
    finding_summary: str
    citation_type:   str


@dataclass
class TracedArbitratorOutput:
    """Structured output of ``ArbitratorEngine.run_with_context()``.

    Carries full provenance as required by the Traceability Standard and the
    Veto Criteria (manifesto.md):

    - Every cited finding is mapped to ``[ArtifactID:SectionID]`` in
      ``provenance_map``.
    - Findings without any ``SourceCitation`` are collected in
      ``unsubstantiated_findings`` and marked ``"Unsubstantiated"``.
    - ``traceability_density`` = cited_findings / total_findings (1.0 if no
      findings exist).
    - All 12 dimensions are summarised in ``dimension_summaries``.
    - ``contradictions`` lists pairs of dimensions that cite the same artifact
      with opposing confidence levels (RED vs GREEN).

    Attributes:
        version_id:               Provenance anchor (FK → versions.id).
        persona_applied:          Persona prompt used for this run.
        user_context_applied:     ``True`` if ``user_context_text`` was non-empty.
        sme_augmentations:        SME augmentation strings applied.
        dimension_summaries:      Per-dimension summary dicts containing
                                  ``dimension``, ``overall_confidence``,
                                  ``finding_count``, ``cited_finding_count``,
                                  and ``provenance_refs``.
        contradictions:           Rule-based contradiction dicts.  Each entry
                                  has ``dimension_a``, ``dimension_b``,
                                  ``artifact_ref``, and ``description``.
        provenance_map:           ``[ArtifactID:SectionID]`` entries for every
                                  cited finding.
        unsubstantiated_findings: Findings lacking ``SourceCitation`` objects.
        traceability_density:     Fraction of findings with ≥1 citation.
    """

    version_id:               str
    persona_applied:          str
    user_context_applied:     bool
    sme_augmentations:        List[str]
    dimension_summaries:      List[dict]
    contradictions:           List[dict]
    provenance_map:           List[ProvenanceEntry]
    unsubstantiated_findings: List[dict]
    traceability_density:     float

    def to_json(self) -> str:
        """Serialise the full output to a JSON string for storage or export.

        Converts all nested dataclasses to plain dicts via
        ``dataclasses.asdict`` so the result is fully JSON-serialisable
        without a custom encoder.

        Returns:
            Compact JSON string containing all provenance fields.
        """
        import dataclasses as _dc

        return json.dumps(_dc.asdict(self))


# ── run_with_context — mock orchestration ─────────────────────────────────────
# Monkey-patched onto ArbitratorEngine so the existing LLM-backed ``run()``
# method is untouched and the mock lives alongside it on the same class.


async def _run_with_context(
    self: "ArbitratorEngine",
    payloads: List[ReviewNodePayload],
    context: ReviewContext,
) -> TracedArbitratorOutput:
    """Mock orchestration — deterministic, no LLM call.

    Processes the 12 ``ReviewNodePayload`` objects together with the
    ``ReviewContext`` (persona, user briefing, SME augmentations) and returns
    a ``TracedArbitratorOutput`` that satisfies the Traceability Standard:

    1. Guard: exactly 12 payloads required.
    2. Guard: ``context.version_id`` must be non-empty.
    3. Build ``provenance_map`` — one ``ProvenanceEntry`` per
       (finding, citation) pair, in ``[ArtifactID:SectionID]`` format.
    4. Collect ``unsubstantiated_findings`` — any finding with no citations.
    5. Calculate ``traceability_density``.
    6. Build per-dimension ``dimension_summaries``.
    7. Detect rule-based ``contradictions``: two dimensions that cite the
       same artifact with opposing confidence (RED vs GREEN).

    Parameters
    ----------
    payloads:
        Exactly 12 validated ``ReviewNodePayload`` objects.
    context:
        ``ReviewContext`` sourced from the ``ReviewRow`` for this run.

    Returns
    -------
    TracedArbitratorOutput
        Fully-populated, JSON-exportable result with complete provenance.

    Raises
    ------
    ArbitratorError
        If ``len(payloads) != 12`` or ``context.version_id`` is empty.
        Both checks run before any processing occurs.
    """
    # ── Guards ────────────────────────────────────────────────────────────────
    if len(payloads) != 12:
        raise ArbitratorError(
            f"run_with_context requires exactly 12 payloads, got {len(payloads)}"
        )
    if not context.version_id or not context.version_id.strip():
        raise ArbitratorError(
            "ReviewContext.version_id must be non-empty (provenance anchor)"
        )

    # ── Step 1: build provenance map and collect unsubstantiated findings ─────
    provenance_map: List[ProvenanceEntry] = []
    unsubstantiated: List[dict] = []

    # artifact_confidence_index: artifact_ref → [(dimension, confidence)]
    # Used for rule-based contradiction detection in step 4.
    artifact_confidence_index: dict[str, List[tuple[str, str]]] = {}

    for payload in payloads:
        dim_value = payload.dimension.value
        for finding in payload.findings:
            if finding.citations:
                for citation in finding.citations:
                    ref = (
                        f"[{citation.file_path}"
                        f":{citation.line_start}-{citation.line_end}]"
                    )
                    provenance_map.append(
                        ProvenanceEntry(
                            artifact_ref=ref,
                            dimension=dim_value,
                            confidence=finding.confidence.value,
                            finding_summary=finding.summary,
                            citation_type=citation.citation_type.value,
                        )
                    )
                    artifact_confidence_index.setdefault(ref, []).append(
                        (dim_value, finding.confidence.value)
                    )
            else:
                unsubstantiated.append(
                    {
                        "dimension": dim_value,
                        "summary": finding.summary,
                        "confidence": finding.confidence.value,
                        "status": "Unsubstantiated",
                    }
                )

    # ── Step 2: calculate traceability density ────────────────────────────────
    all_findings = [f for p in payloads for f in p.findings]
    cited_findings = [f for f in all_findings if f.citations]
    traceability_density = (
        len(cited_findings) / len(all_findings) if all_findings else 1.0
    )

    # ── Step 3: per-dimension summaries ──────────────────────────────────────
    dimension_summaries: List[dict] = []
    for payload in payloads:
        dim_refs: List[str] = []
        for finding in payload.findings:
            for citation in finding.citations:
                dim_refs.append(
                    f"[{citation.file_path}"
                    f":{citation.line_start}-{citation.line_end}]"
                )
        dimension_summaries.append(
            {
                "dimension": payload.dimension.value,
                "overall_confidence": payload.overall_confidence.value,
                "finding_count": len(payload.findings),
                "cited_finding_count": sum(
                    1 for f in payload.findings if f.citations
                ),
                "provenance_refs": dim_refs,
            }
        )

    # ── Step 4: rule-based contradiction detection ────────────────────────────
    # A contradiction exists when two different dimensions cite the same
    # artifact with opposing confidence levels: one RED and one GREEN.
    contradictions: List[dict] = []
    _seen_pairs: set[frozenset[str]] = set()

    for ref, entries in artifact_confidence_index.items():
        if len(entries) < 2:
            continue
        dims_by_confidence: dict[str, List[str]] = {}
        for dim_name, conf in entries:
            dims_by_confidence.setdefault(conf, []).append(dim_name)

        red_dims = dims_by_confidence.get("RED", [])
        green_dims = dims_by_confidence.get("GREEN", [])

        for dim_a in red_dims:
            for dim_b in green_dims:
                pair = frozenset({dim_a, dim_b})
                if pair in _seen_pairs:
                    continue
                _seen_pairs.add(pair)
                contradictions.append(
                    {
                        "dimension_a": dim_a,
                        "dimension_b": dim_b,
                        "artifact_ref": ref,
                        "description": (
                            f"{dim_a} rates {ref} RED while "
                            f"{dim_b} rates the same artifact GREEN."
                        ),
                    }
                )

    return TracedArbitratorOutput(
        version_id=context.version_id,
        persona_applied=context.persona_prompt,
        user_context_applied=bool(context.user_context_text.strip()),
        sme_augmentations=list(context.sme_augmentation_list),
        dimension_summaries=dimension_summaries,
        contradictions=contradictions,
        provenance_map=provenance_map,
        unsubstantiated_findings=unsubstantiated,
        traceability_density=round(traceability_density, 4),
    )


# Attach to ArbitratorEngine so callers use engine.run_with_context(...)
ArbitratorEngine.run_with_context = _run_with_context  # type: ignore[attr-defined]
