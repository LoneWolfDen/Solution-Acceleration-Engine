"""Tests for contexta/pipeline/confidence.py.

Coverage areas
--------------
- SDLCPhase and ITILPhase enum completeness.
- DIMENSION_SDLC_MAP: all 12 dimensions present, specific mappings verified.
- DIMENSION_ITIL_MAP: all 12 dimensions present, specific mappings verified.
- ConfidenceEngine input validation (raises on != 12 payloads).
- Uniform confidence scores (all GREEN / AMBER / RED).
- Aggregate counts (red / amber / green).
- DimensionScore contents (numeric_score, phase lists, confidence, dimension).
- SDLC phase score arithmetic (exact averages, phase isolation).
- ITIL phase score arithmetic (exact averages).
- ConfidenceMatrix JSON serialisation and round-trip.
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
from contexta.pipeline.confidence import (
    DIMENSION_ITIL_MAP,
    DIMENSION_SDLC_MAP,
    ConfidenceEngine,
    ConfidenceEngineError,
    ConfidenceMatrix,
    DimensionScore,
    ITILPhase,
    SDLCPhase,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _payload(
    dim: ReviewDimensionEnum,
    overall: ConfidenceEnum,
) -> ReviewNodePayload:
    """Minimal valid payload for a single dimension."""
    return ReviewNodePayload(
        dimension=dim,
        findings=[],
        overall_confidence=overall,
        raw_llm_response="{}",
    )


def _all_payloads(overall: ConfidenceEnum) -> List[ReviewNodePayload]:
    """Return 12 payloads with the same overall confidence, one per dimension."""
    return [_payload(dim, overall) for dim in ReviewDimensionEnum]


def _payloads_with_override(
    default: ConfidenceEnum,
    overrides: Dict[ReviewDimensionEnum, ConfidenceEnum],
) -> List[ReviewNodePayload]:
    """Build 12 payloads, applying per-dimension overrides over a default."""
    return [
        _payload(dim, overrides.get(dim, default))
        for dim in ReviewDimensionEnum
    ]


# ── TestPhaseEnums ────────────────────────────────────────────────────────────

class TestPhaseEnums:
    def test_sdlc_has_7_phases(self):
        assert len(list(SDLCPhase)) == 7

    def test_itil_has_5_phases(self):
        assert len(list(ITILPhase)) == 5

    def test_sdlc_planning_value(self):
        assert SDLCPhase.PLANNING.value == "Planning"

    def test_sdlc_operations_value(self):
        assert SDLCPhase.OPERATIONS.value == "Operations"

    def test_itil_strategy_value(self):
        assert ITILPhase.STRATEGY.value == "Strategy"

    def test_itil_continual_improvement_value(self):
        assert ITILPhase.CONTINUAL_IMPROVEMENT.value == "Continual Improvement"

    def test_sdlc_phase_is_str_enum(self):
        for phase in SDLCPhase:
            assert isinstance(phase, str)

    def test_itil_phase_is_str_enum(self):
        for phase in ITILPhase:
            assert isinstance(phase, str)


# ── TestDimensionSDLCMapping ──────────────────────────────────────────────────

class TestDimensionSDLCMapping:
    def test_all_12_dimensions_present(self):
        assert set(DIMENSION_SDLC_MAP.keys()) == set(ReviewDimensionEnum)

    def test_intent_maps_to_planning_and_requirements(self):
        phases = DIMENSION_SDLC_MAP[ReviewDimensionEnum.INTENT]
        assert SDLCPhase.PLANNING in phases
        assert SDLCPhase.REQUIREMENTS in phases

    def test_scope_maps_to_planning_and_requirements(self):
        phases = DIMENSION_SDLC_MAP[ReviewDimensionEnum.SCOPE]
        assert SDLCPhase.PLANNING in phases
        assert SDLCPhase.REQUIREMENTS in phases

    def test_delivery_maps_to_development_testing_deployment(self):
        phases = DIMENSION_SDLC_MAP[ReviewDimensionEnum.DELIVERY]
        assert SDLCPhase.DEVELOPMENT in phases
        assert SDLCPhase.TESTING in phases
        assert SDLCPhase.DEPLOYMENT in phases

    def test_architecture_maps_to_design_and_development(self):
        phases = DIMENSION_SDLC_MAP[ReviewDimensionEnum.ARCHITECTURE]
        assert SDLCPhase.DESIGN in phases
        assert SDLCPhase.DEVELOPMENT in phases

    def test_nfr_maps_to_requirements_design_testing(self):
        phases = DIMENSION_SDLC_MAP[ReviewDimensionEnum.NFR]
        assert SDLCPhase.REQUIREMENTS in phases
        assert SDLCPhase.DESIGN in phases
        assert SDLCPhase.TESTING in phases

    def test_risk_maps_to_four_sdlc_phases(self):
        phases = DIMENSION_SDLC_MAP[ReviewDimensionEnum.RISK]
        assert len(phases) == 4
        assert SDLCPhase.PLANNING in phases
        assert SDLCPhase.DESIGN in phases
        assert SDLCPhase.TESTING in phases
        assert SDLCPhase.OPERATIONS in phases

    def test_commercial_maps_only_to_planning(self):
        phases = DIMENSION_SDLC_MAP[ReviewDimensionEnum.COMMERCIAL]
        assert phases == [SDLCPhase.PLANNING]

    def test_consistency_maps_to_testing_and_operations(self):
        phases = DIMENSION_SDLC_MAP[ReviewDimensionEnum.CONSISTENCY]
        assert SDLCPhase.TESTING in phases
        assert SDLCPhase.OPERATIONS in phases

    def test_all_values_are_sdlc_phase_instances(self):
        for phases in DIMENSION_SDLC_MAP.values():
            for p in phases:
                assert isinstance(p, SDLCPhase)

    def test_planning_has_7_contributing_dimensions(self):
        count = sum(
            1 for phases in DIMENSION_SDLC_MAP.values()
            if SDLCPhase.PLANNING in phases
        )
        assert count == 7


# ── TestDimensionITILMapping ──────────────────────────────────────────────────

class TestDimensionITILMapping:
    def test_all_12_dimensions_present(self):
        assert set(DIMENSION_ITIL_MAP.keys()) == set(ReviewDimensionEnum)

    def test_intent_maps_only_to_strategy(self):
        phases = DIMENSION_ITIL_MAP[ReviewDimensionEnum.INTENT]
        assert phases == [ITILPhase.STRATEGY]

    def test_risk_maps_to_all_5_itil_phases(self):
        phases = DIMENSION_ITIL_MAP[ReviewDimensionEnum.RISK]
        assert len(phases) == 5
        assert set(phases) == set(ITILPhase)

    def test_architecture_maps_only_to_design(self):
        phases = DIMENSION_ITIL_MAP[ReviewDimensionEnum.ARCHITECTURE]
        assert phases == [ITILPhase.DESIGN]

    def test_consistency_maps_only_to_continual_improvement(self):
        phases = DIMENSION_ITIL_MAP[ReviewDimensionEnum.CONSISTENCY]
        assert phases == [ITILPhase.CONTINUAL_IMPROVEMENT]

    def test_commercial_maps_only_to_strategy(self):
        phases = DIMENSION_ITIL_MAP[ReviewDimensionEnum.COMMERCIAL]
        assert phases == [ITILPhase.STRATEGY]

    def test_timeline_maps_only_to_transition(self):
        phases = DIMENSION_ITIL_MAP[ReviewDimensionEnum.TIMELINE]
        assert phases == [ITILPhase.TRANSITION]

    def test_language_maps_only_to_design(self):
        phases = DIMENSION_ITIL_MAP[ReviewDimensionEnum.LANGUAGE]
        assert phases == [ITILPhase.DESIGN]

    def test_delivery_maps_to_transition_and_operation(self):
        phases = DIMENSION_ITIL_MAP[ReviewDimensionEnum.DELIVERY]
        assert ITILPhase.TRANSITION in phases
        assert ITILPhase.OPERATION in phases

    def test_all_values_are_itil_phase_instances(self):
        for phases in DIMENSION_ITIL_MAP.values():
            for p in phases:
                assert isinstance(p, ITILPhase)

    def test_strategy_has_6_contributing_dimensions(self):
        count = sum(
            1 for phases in DIMENSION_ITIL_MAP.values()
            if ITILPhase.STRATEGY in phases
        )
        assert count == 6


# ── TestConfidenceEngineInputValidation ──────────────────────────────────────

class TestConfidenceEngineInputValidation:
    def setup_method(self):
        self.engine = ConfidenceEngine()

    def test_raises_on_zero_payloads(self):
        with pytest.raises(ConfidenceEngineError):
            self.engine.compute([])

    def test_raises_on_11_payloads(self):
        payloads = _all_payloads(ConfidenceEnum.GREEN)[:11]
        with pytest.raises(ConfidenceEngineError):
            self.engine.compute(payloads)

    def test_raises_on_13_payloads(self):
        payloads = _all_payloads(ConfidenceEnum.GREEN)
        extra = _payload(ReviewDimensionEnum.INTENT, ConfidenceEnum.GREEN)
        with pytest.raises(ConfidenceEngineError):
            self.engine.compute(payloads + [extra])

    def test_error_message_contains_actual_count(self):
        with pytest.raises(ConfidenceEngineError, match="11"):
            self.engine.compute(_all_payloads(ConfidenceEnum.GREEN)[:11])

    def test_raises_confidence_engine_error_type(self):
        with pytest.raises(ConfidenceEngineError):
            self.engine.compute([])

    def test_exact_12_payloads_does_not_raise(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        assert isinstance(matrix, ConfidenceMatrix)


# ── TestConfidenceEngineUniformScores ────────────────────────────────────────

class TestConfidenceEngineUniformScores:
    def setup_method(self):
        self.engine = ConfidenceEngine()

    def test_all_green_overall_score_is_3(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        assert matrix.overall_score == 3.0

    def test_all_red_overall_score_is_1(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.RED))
        assert matrix.overall_score == 1.0

    def test_all_amber_overall_score_is_2(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.AMBER))
        assert matrix.overall_score == 2.0

    def test_all_green_sdlc_scores_are_3(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        for phase, score in matrix.sdlc_phase_scores.items():
            assert score == 3.0, f"{phase} expected 3.0 got {score}"

    def test_all_red_sdlc_scores_are_1(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.RED))
        for phase, score in matrix.sdlc_phase_scores.items():
            assert score == 1.0, f"{phase} expected 1.0 got {score}"

    def test_all_amber_sdlc_scores_are_2(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.AMBER))
        for phase, score in matrix.sdlc_phase_scores.items():
            assert score == 2.0, f"{phase} expected 2.0 got {score}"

    def test_all_green_itil_scores_are_3(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        for phase, score in matrix.itil_phase_scores.items():
            assert score == 3.0, f"{phase} expected 3.0 got {score}"

    def test_all_red_itil_scores_are_1(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.RED))
        for phase, score in matrix.itil_phase_scores.items():
            assert score == 1.0, f"{phase} expected 1.0 got {score}"

    def test_all_amber_itil_scores_are_2(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.AMBER))
        for phase, score in matrix.itil_phase_scores.items():
            assert score == 2.0, f"{phase} expected 2.0 got {score}"


# ── TestConfidenceEngineAggregateCounts ──────────────────────────────────────

class TestConfidenceEngineAggregateCounts:
    def setup_method(self):
        self.engine = ConfidenceEngine()

    def test_all_green_green_count_is_12(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        assert matrix.green_count == 12

    def test_all_green_red_count_is_0(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        assert matrix.red_count == 0

    def test_all_green_amber_count_is_0(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        assert matrix.amber_count == 0

    def test_all_red_red_count_is_12(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.RED))
        assert matrix.red_count == 12

    def test_all_amber_amber_count_is_12(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.AMBER))
        assert matrix.amber_count == 12

    def test_counts_sum_to_12_for_mixed(self):
        payloads = _payloads_with_override(
            ConfidenceEnum.GREEN,
            {
                ReviewDimensionEnum.RISK: ConfidenceEnum.RED,
                ReviewDimensionEnum.SCOPE: ConfidenceEnum.AMBER,
            },
        )
        matrix = self.engine.compute(payloads)
        assert matrix.red_count + matrix.amber_count + matrix.green_count == 12

    def test_specific_mixed_counts(self):
        payloads = _payloads_with_override(
            ConfidenceEnum.GREEN,
            {
                ReviewDimensionEnum.RISK: ConfidenceEnum.RED,
                ReviewDimensionEnum.SCOPE: ConfidenceEnum.RED,
                ReviewDimensionEnum.TIMELINE: ConfidenceEnum.AMBER,
            },
        )
        matrix = self.engine.compute(payloads)
        assert matrix.red_count == 2
        assert matrix.amber_count == 1
        assert matrix.green_count == 9


# ── TestDimensionScoreContents ────────────────────────────────────────────────

class TestDimensionScoreContents:
    def setup_method(self):
        self.engine = ConfidenceEngine()

    def test_dimension_scores_count_is_12(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        assert len(matrix.dimension_scores) == 12

    def test_green_payload_numeric_score_is_3(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        for ds in matrix.dimension_scores:
            assert ds.numeric_score == 3

    def test_amber_payload_numeric_score_is_2(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.AMBER))
        for ds in matrix.dimension_scores:
            assert ds.numeric_score == 2

    def test_red_payload_numeric_score_is_1(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.RED))
        for ds in matrix.dimension_scores:
            assert ds.numeric_score == 1

    def test_dimension_score_has_non_empty_sdlc_phases(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        for ds in matrix.dimension_scores:
            assert len(ds.sdlc_phases) > 0

    def test_dimension_score_has_non_empty_itil_phases(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        for ds in matrix.dimension_scores:
            assert len(ds.itil_phases) > 0

    def test_dimension_score_confidence_matches_input(self):
        payloads = _all_payloads(ConfidenceEnum.AMBER)
        matrix = self.engine.compute(payloads)
        for ds in matrix.dimension_scores:
            assert ds.overall_confidence == ConfidenceEnum.AMBER

    def test_dimension_field_matches_payload_dimension(self):
        payloads = _all_payloads(ConfidenceEnum.GREEN)
        matrix = self.engine.compute(payloads)
        input_dims = {p.dimension for p in payloads}
        output_dims = {ds.dimension for ds in matrix.dimension_scores}
        assert input_dims == output_dims

    def test_risk_dimension_score_maps_to_all_sdlc_risk_phases(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        risk_score = next(ds for ds in matrix.dimension_scores
                          if ds.dimension == ReviewDimensionEnum.RISK)
        assert SDLCPhase.PLANNING in risk_score.sdlc_phases
        assert SDLCPhase.OPERATIONS in risk_score.sdlc_phases

    def test_risk_dimension_score_maps_to_all_5_itil_phases(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.GREEN))
        risk_score = next(ds for ds in matrix.dimension_scores
                          if ds.dimension == ReviewDimensionEnum.RISK)
        assert set(risk_score.itil_phases) == set(ITILPhase)


# ── TestSDLCPhaseScores ───────────────────────────────────────────────────────

class TestSDLCPhaseScores:
    """Verify exact phase averages when RISK=RED and all other dims=GREEN.

    Pre-computed exact values (see test_confidence.py module docstring):
      Planning:     19/7 = 2.714   (RISK contributes)
      Requirements: 12/4 = 3.0     (RISK does NOT contribute)
      Design:       13/5 = 2.6     (RISK contributes)
      Development:  12/4 = 3.0     (RISK does NOT contribute)
      Testing:      10/4 = 2.5     (RISK contributes)
      Deployment:    3/1 = 3.0     (RISK does NOT contribute)
      Operations:    4/2 = 2.0     (RISK contributes)
    """

    def setup_method(self):
        self.engine = ConfidenceEngine()
        payloads = _payloads_with_override(
            ConfidenceEnum.GREEN,
            {ReviewDimensionEnum.RISK: ConfidenceEnum.RED},
        )
        self.matrix = self.engine.compute(payloads)

    def test_planning_score_reduced_by_risk_red(self):
        assert self.matrix.sdlc_phase_scores[SDLCPhase.PLANNING.value] == 2.714

    def test_requirements_score_unaffected_by_risk(self):
        assert self.matrix.sdlc_phase_scores[SDLCPhase.REQUIREMENTS.value] == 3.0

    def test_design_score_reduced_by_risk_red(self):
        assert self.matrix.sdlc_phase_scores[SDLCPhase.DESIGN.value] == 2.6

    def test_development_score_unaffected_by_risk(self):
        assert self.matrix.sdlc_phase_scores[SDLCPhase.DEVELOPMENT.value] == 3.0

    def test_testing_score_reduced_by_risk_red(self):
        assert self.matrix.sdlc_phase_scores[SDLCPhase.TESTING.value] == 2.5

    def test_deployment_score_unaffected_by_risk(self):
        assert self.matrix.sdlc_phase_scores[SDLCPhase.DEPLOYMENT.value] == 3.0

    def test_operations_score_reduced_to_2(self):
        assert self.matrix.sdlc_phase_scores[SDLCPhase.OPERATIONS.value] == 2.0

    def test_sdlc_keys_match_sdlc_phase_values(self):
        expected_keys = {p.value for p in SDLCPhase}
        assert set(self.matrix.sdlc_phase_scores.keys()) == expected_keys

    def test_overall_score_with_one_red(self):
        # 11 GREEN (3) + 1 RED (1) = 34/12 = 2.833
        assert self.matrix.overall_score == 2.833

    def test_all_amber_planning_score_is_2(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.AMBER))
        assert matrix.sdlc_phase_scores[SDLCPhase.PLANNING.value] == 2.0


# ── TestITILPhaseScores ───────────────────────────────────────────────────────

class TestITILPhaseScores:
    """Verify exact ITIL phase averages when RISK=RED and all other dims=GREEN.

    Pre-computed exact values:
      Strategy:              16/6 = 2.667
      Design:                13/5 = 2.6
      Transition:            13/5 = 2.6
      Operation:              7/3 = 2.333
      Continual Improvement:  4/2 = 2.0
    """

    def setup_method(self):
        self.engine = ConfidenceEngine()
        payloads = _payloads_with_override(
            ConfidenceEnum.GREEN,
            {ReviewDimensionEnum.RISK: ConfidenceEnum.RED},
        )
        self.matrix = self.engine.compute(payloads)

    def test_strategy_score_reduced_by_risk_red(self):
        assert self.matrix.itil_phase_scores[ITILPhase.STRATEGY.value] == 2.667

    def test_design_score_reduced_by_risk_red(self):
        assert self.matrix.itil_phase_scores[ITILPhase.DESIGN.value] == 2.6

    def test_transition_score_reduced_by_risk_red(self):
        assert self.matrix.itil_phase_scores[ITILPhase.TRANSITION.value] == 2.6

    def test_operation_score_reduced_by_risk_red(self):
        assert self.matrix.itil_phase_scores[ITILPhase.OPERATION.value] == 2.333

    def test_continual_improvement_score_reduced_to_2(self):
        assert self.matrix.itil_phase_scores[ITILPhase.CONTINUAL_IMPROVEMENT.value] == 2.0

    def test_itil_keys_match_itil_phase_values(self):
        expected_keys = {p.value for p in ITILPhase}
        assert set(self.matrix.itil_phase_scores.keys()) == expected_keys

    def test_all_amber_strategy_score_is_2(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.AMBER))
        assert matrix.itil_phase_scores[ITILPhase.STRATEGY.value] == 2.0

    def test_all_amber_continual_improvement_score_is_2(self):
        matrix = self.engine.compute(_all_payloads(ConfidenceEnum.AMBER))
        assert matrix.itil_phase_scores[ITILPhase.CONTINUAL_IMPROVEMENT.value] == 2.0

    def test_risk_red_affects_all_5_itil_phases(self):
        # Every ITIL phase should be below 3.0 since RISK contributes to all.
        for phase_score in self.matrix.itil_phase_scores.values():
            assert phase_score < 3.0


# ── TestConfidenceMatrixSerialization ────────────────────────────────────────

class TestConfidenceMatrixSerialization:
    def setup_method(self):
        self.engine = ConfidenceEngine()
        self.matrix = self.engine.compute(_all_payloads(ConfidenceEnum.AMBER))

    def test_model_dump_json_is_valid_json(self):
        raw = self.matrix.model_dump_json()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_round_trip_preserves_overall_score(self):
        raw = self.matrix.model_dump_json()
        restored = ConfidenceMatrix.model_validate_json(raw)
        assert restored.overall_score == self.matrix.overall_score

    def test_round_trip_preserves_dimension_scores_count(self):
        raw = self.matrix.model_dump_json()
        restored = ConfidenceMatrix.model_validate_json(raw)
        assert len(restored.dimension_scores) == 12

    def test_round_trip_preserves_counts(self):
        raw = self.matrix.model_dump_json()
        restored = ConfidenceMatrix.model_validate_json(raw)
        assert restored.red_count == self.matrix.red_count
        assert restored.amber_count == self.matrix.amber_count
        assert restored.green_count == self.matrix.green_count

    def test_round_trip_preserves_sdlc_phase_scores(self):
        raw = self.matrix.model_dump_json()
        restored = ConfidenceMatrix.model_validate_json(raw)
        assert restored.sdlc_phase_scores == self.matrix.sdlc_phase_scores

    def test_round_trip_preserves_itil_phase_scores(self):
        raw = self.matrix.model_dump_json()
        restored = ConfidenceMatrix.model_validate_json(raw)
        assert restored.itil_phase_scores == self.matrix.itil_phase_scores

    def test_generated_at_is_iso8601(self):
        from datetime import datetime
        datetime.fromisoformat(self.matrix.generated_at)  # raises if malformed

    def test_sdlc_phases_preserved_in_dimension_scores_round_trip(self):
        raw = self.matrix.model_dump_json()
        restored = ConfidenceMatrix.model_validate_json(raw)
        orig_phases = {ds.dimension: ds.sdlc_phases for ds in self.matrix.dimension_scores}
        rest_phases = {ds.dimension: ds.sdlc_phases for ds in restored.dimension_scores}
        assert orig_phases == rest_phases
