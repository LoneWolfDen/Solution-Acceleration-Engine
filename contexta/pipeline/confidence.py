"""Confidence Engine — SDLC / ITIL scoring matrix across 12 review dimensions.

``ConfidenceEngine.compute()`` accepts a list of 12 ``ReviewNodePayload``
objects and returns a ``ConfidenceMatrix`` that:

- Maps every ``ReviewDimensionEnum`` to its SDLC and ITIL phases.
- Assigns a numeric score per dimension: GREEN=3, AMBER=2, RED=1.
- Computes per-phase average scores for both frameworks.
- Reports aggregate counts (red / amber / green) and an overall score.

Manifesto compliance
--------------------
- Source ``[ArtifactID:SectionID]`` references in each
  ``ReviewNodePayload`` are *not* discarded — the payloads that drive
  scoring are the same validated objects stored by the pipeline.
- ``ConfidenceMatrix`` is a Pydantic model; ``model_dump_json()`` produces
  a fully self-contained, JSON-exportable artefact.
- No TUI dependencies — pure analytical pipeline logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List

from pydantic import BaseModel

from ..models.enums import ConfidenceEnum, ReviewDimensionEnum
from ..models.payloads import ReviewNodePayload


# ── Phase enums ───────────────────────────────────────────────────────────────

class SDLCPhase(str, Enum):
    """Standard SDLC phases used by the Confidence Engine X/Y matrix."""

    PLANNING     = "Planning"
    REQUIREMENTS = "Requirements"
    DESIGN       = "Design"
    DEVELOPMENT  = "Development"
    TESTING      = "Testing"
    DEPLOYMENT   = "Deployment"
    OPERATIONS   = "Operations"


class ITILPhase(str, Enum):
    """ITIL v4 service management phases used by the Confidence Engine X/Y matrix."""

    STRATEGY             = "Strategy"
    DESIGN               = "Design"
    TRANSITION           = "Transition"
    OPERATION            = "Operation"
    CONTINUAL_IMPROVEMENT = "Continual Improvement"


# ── Dimension → Phase mappings ────────────────────────────────────────────────

DIMENSION_SDLC_MAP: Dict[ReviewDimensionEnum, List[SDLCPhase]] = {
    ReviewDimensionEnum.INTENT:        [SDLCPhase.PLANNING,     SDLCPhase.REQUIREMENTS],
    ReviewDimensionEnum.SCOPE:         [SDLCPhase.PLANNING,     SDLCPhase.REQUIREMENTS],
    ReviewDimensionEnum.OWNERSHIP:     [SDLCPhase.PLANNING,     SDLCPhase.DESIGN],
    ReviewDimensionEnum.DELIVERY:      [SDLCPhase.DEVELOPMENT,  SDLCPhase.TESTING,       SDLCPhase.DEPLOYMENT],
    ReviewDimensionEnum.TIMELINE:      [SDLCPhase.PLANNING,     SDLCPhase.DEVELOPMENT],
    ReviewDimensionEnum.ARCHITECTURE:  [SDLCPhase.DESIGN,       SDLCPhase.DEVELOPMENT],
    ReviewDimensionEnum.NFR:           [SDLCPhase.REQUIREMENTS, SDLCPhase.DESIGN,         SDLCPhase.TESTING],
    ReviewDimensionEnum.RESOURCE:      [SDLCPhase.PLANNING,     SDLCPhase.DEVELOPMENT],
    ReviewDimensionEnum.RISK:          [SDLCPhase.PLANNING,     SDLCPhase.DESIGN,
                                        SDLCPhase.TESTING,      SDLCPhase.OPERATIONS],
    ReviewDimensionEnum.COMMERCIAL:    [SDLCPhase.PLANNING],
    ReviewDimensionEnum.LANGUAGE:      [SDLCPhase.REQUIREMENTS, SDLCPhase.DESIGN],
    ReviewDimensionEnum.CONSISTENCY:   [SDLCPhase.TESTING,      SDLCPhase.OPERATIONS],
}

DIMENSION_ITIL_MAP: Dict[ReviewDimensionEnum, List[ITILPhase]] = {
    ReviewDimensionEnum.INTENT:        [ITILPhase.STRATEGY],
    ReviewDimensionEnum.SCOPE:         [ITILPhase.STRATEGY,   ITILPhase.DESIGN],
    ReviewDimensionEnum.OWNERSHIP:     [ITILPhase.STRATEGY,   ITILPhase.TRANSITION],
    ReviewDimensionEnum.DELIVERY:      [ITILPhase.TRANSITION, ITILPhase.OPERATION],
    ReviewDimensionEnum.TIMELINE:      [ITILPhase.TRANSITION],
    ReviewDimensionEnum.ARCHITECTURE:  [ITILPhase.DESIGN],
    ReviewDimensionEnum.NFR:           [ITILPhase.DESIGN,     ITILPhase.OPERATION],
    ReviewDimensionEnum.RESOURCE:      [ITILPhase.STRATEGY,   ITILPhase.TRANSITION],
    ReviewDimensionEnum.RISK:          [ITILPhase.STRATEGY,   ITILPhase.DESIGN,
                                        ITILPhase.TRANSITION, ITILPhase.OPERATION,
                                        ITILPhase.CONTINUAL_IMPROVEMENT],
    ReviewDimensionEnum.COMMERCIAL:    [ITILPhase.STRATEGY],
    ReviewDimensionEnum.LANGUAGE:      [ITILPhase.DESIGN],
    ReviewDimensionEnum.CONSISTENCY:   [ITILPhase.CONTINUAL_IMPROVEMENT],
}


# ── Numeric scoring ───────────────────────────────────────────────────────────

_CONFIDENCE_NUMERIC: Dict[ConfidenceEnum, int] = {
    ConfidenceEnum.RED:   1,
    ConfidenceEnum.AMBER: 2,
    ConfidenceEnum.GREEN: 3,
}


# ── Output models ─────────────────────────────────────────────────────────────

class DimensionScore(BaseModel):
    """Confidence score for one dimension with its SDLC and ITIL phase coverage.

    ``numeric_score`` encodes the confidence level as an integer:
    RED=1, AMBER=2, GREEN=3.  Phase lists reflect the static mapping
    constants ``DIMENSION_SDLC_MAP`` and ``DIMENSION_ITIL_MAP``.
    """

    dimension:          ReviewDimensionEnum
    overall_confidence: ConfidenceEnum
    numeric_score:      int
    sdlc_phases:        List[SDLCPhase]
    itil_phases:        List[ITILPhase]


class ConfidenceMatrix(BaseModel):
    """X/Y confidence scoring matrix across all 12 review dimensions.

    X axis — ``ReviewDimensionEnum`` (12 values).
    Y axis — ``SDLCPhase`` (7 values) and ``ITILPhase`` (5 values).

    Phase scores are computed as the arithmetic mean of the ``numeric_score``
    values of all dimensions mapped to that phase.  Phases with no dimension
    mapped to them receive a score of ``0.0``.

    Manifesto compliance
    --------------------
    - All source ``[ArtifactID:SectionID]`` references are retained in the
      originating ``ReviewNodePayload`` objects; this model reports derived
      aggregate scores only.
    - Fully JSON-exportable via ``model_dump_json()``.
    """

    dimension_scores:   List[DimensionScore]
    sdlc_phase_scores:  Dict[str, float]   # SDLCPhase.value  -> avg numeric score
    itil_phase_scores:  Dict[str, float]   # ITILPhase.value  -> avg numeric score
    overall_score:      float              # mean numeric score across all 12 dimensions
    red_count:          int
    amber_count:        int
    green_count:        int
    generated_at:       str               # ISO-8601 UTC


# ── Engine ────────────────────────────────────────────────────────────────────

class ConfidenceEngineError(Exception):
    """Raised when ``ConfidenceEngine.compute()`` receives invalid input."""


class ConfidenceEngine:
    """Computes an X/Y confidence matrix across the 12 review dimensions.

    Dimensions are mapped to SDLC and ITIL phases via the module-level
    ``DIMENSION_SDLC_MAP`` and ``DIMENSION_ITIL_MAP`` constants.

    Phase scores are the arithmetic mean of the numeric scores of all
    dimensions that contribute to that phase.

    Usage
    -----
    ::

        engine = ConfidenceEngine()
        matrix = engine.compute(payloads)
        json_str = matrix.model_dump_json()
    """

    def compute(self, payloads: List[ReviewNodePayload]) -> ConfidenceMatrix:
        """Compute the confidence matrix from 12 dimension payloads.

        Parameters
        ----------
        payloads:
            ``ReviewNodePayload`` objects — exactly one per
            ``ReviewDimensionEnum``.

        Returns
        -------
        ConfidenceMatrix
            Full scoring matrix with per-dimension scores, SDLC/ITIL phase
            averages, aggregate counts, and ISO-8601 timestamp.

        Raises
        ------
        ConfidenceEngineError
            If ``len(payloads) != 12``.
        """
        if len(payloads) != 12:
            raise ConfidenceEngineError(
                f"ConfidenceEngine requires exactly 12 payloads, got {len(payloads)}"
            )

        dimension_scores: List[DimensionScore] = []
        red_count = amber_count = green_count = 0

        # Accumulate numeric scores per SDLC and ITIL phase.
        sdlc_acc: Dict[str, List[int]] = {p.value: [] for p in SDLCPhase}
        itil_acc: Dict[str, List[int]] = {p.value: [] for p in ITILPhase}

        for payload in payloads:
            dim  = payload.dimension
            conf = payload.overall_confidence
            score = _CONFIDENCE_NUMERIC[conf]

            sdlc_phases = DIMENSION_SDLC_MAP.get(dim, [])
            itil_phases = DIMENSION_ITIL_MAP.get(dim, [])

            dimension_scores.append(
                DimensionScore(
                    dimension=dim,
                    overall_confidence=conf,
                    numeric_score=score,
                    sdlc_phases=sdlc_phases,
                    itil_phases=itil_phases,
                )
            )

            if conf == ConfidenceEnum.RED:
                red_count += 1
            elif conf == ConfidenceEnum.AMBER:
                amber_count += 1
            else:
                green_count += 1

            for phase in sdlc_phases:
                sdlc_acc[phase.value].append(score)
            for phase in itil_phases:
                itil_acc[phase.value].append(score)

        overall_score = sum(ds.numeric_score for ds in dimension_scores) / len(dimension_scores)

        sdlc_phase_scores: Dict[str, float] = {
            phase: round(sum(scores) / len(scores), 3) if scores else 0.0
            for phase, scores in sdlc_acc.items()
        }
        itil_phase_scores: Dict[str, float] = {
            phase: round(sum(scores) / len(scores), 3) if scores else 0.0
            for phase, scores in itil_acc.items()
        }

        return ConfidenceMatrix(
            dimension_scores=dimension_scores,
            sdlc_phase_scores=sdlc_phase_scores,
            itil_phase_scores=itil_phase_scores,
            overall_score=round(overall_score, 3),
            red_count=red_count,
            amber_count=amber_count,
            green_count=green_count,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
