"""Layer 2 synthesis data contracts.

Defines the Pydantic models for the ReconciliationReport produced by the
LayerTwoArbitrator synthesis pipeline.  These models are the authoritative
schema for Layer 2 output — they are used for LLM response validation, DB
persistence (via metadata_json), and export serialisation.

Sprint 6 additions
------------------
GateCheckResult, JudgeValidationReport, and evaluate_reconciliation_report
implement the Judge Validation layer that the PromptOptimizer consumes.
The 6 quality gates allow the PromptOptimizer to pinpoint exactly which gate
triggered a failure and generate targeted prompt adjustment deltas.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DimensionConflict(BaseModel):
    dimensions_involved: List[str] = Field(
        description="The names of the dimensions in conflict (e.g., ['Timeline', 'Resources'])"
    )
    description: str = Field(
        description="Clear explanation of why these dimensions are conflicting."
    )
    severity: str = Field(
        description="Must be 'Low', 'Medium', 'High', or 'Critical'."
    )
    source_references: List[str] = Field(
        default_factory=list,
        description="Specific citations (e.g., 'SOW Slide 4') where the conflicting data was found.",
    )
    suggested_mitigation: str = Field(
        description="Practical steps to resolve this specific conflict."
    )


class ReconciliationReport(BaseModel):
    executive_summary: str = Field(
        description="A high-level, candid synthesis of the overall project viability."
    )
    delivery_confidence_score: int = Field(
        description=(
            "A score from 1 to 100 representing the likelihood of successful delivery "
            "based on current parameters."
        ),
        ge=1,
        le=100,
    )
    critical_conflicts: List[DimensionConflict] = Field(
        default_factory=list,
        description="A list of identified friction points between different project dimensions.",
    )
    architectural_risks: List[str] = Field(
        default_factory=list,
        description="Key technical or architectural risks that could derail the project.",
    )
    actionable_recommendations: List[str] = Field(
        description=(
            "Sequential, actionable steps to unblock the proposal or improve "
            "the delivery baseline."
        )
    )
    ready_for_approval: bool = Field(
        description=(
            "Boolean flag indicating if the proposal is structurally sound enough to proceed."
        )
    )


# ── Sprint 6: Judge Validation ────────────────────────────────────────────────

# Gate thresholds — centralised here so tests and the optimizer can import them.
GATE_DELIVERY_CONFIDENCE_THRESHOLD: int = 60
GATE_MAX_CRITICAL_CONFLICTS: int = 3
GATE_EXECUTIVE_SUMMARY_MIN_LENGTH: int = 50


class GateNameEnum(str, Enum):
    """Names of the 6 quality gates evaluated by evaluate_reconciliation_report()."""

    APPROVAL_GATE = "APPROVAL_GATE"
    DELIVERY_CONFIDENCE = "DELIVERY_CONFIDENCE"
    CONFLICT_SEVERITY_CONTROL = "CONFLICT_SEVERITY_CONTROL"
    CONFLICT_COUNT_BOUNDED = "CONFLICT_COUNT_BOUNDED"
    RECOMMENDATIONS_PRESENT = "RECOMMENDATIONS_PRESENT"
    EXECUTIVE_SUMMARY_SUBSTANTIVE = "EXECUTIVE_SUMMARY_SUBSTANTIVE"


class GateCheckResult(BaseModel):
    """Pass/fail result for a single quality gate.

    Attributes:
        gate_name:        Name of the gate (GateNameEnum value).
        passed:           True if the gate condition was satisfied.
        rejection_reason: Human-readable explanation when passed=False; None when passed=True.
    """

    gate_name: str = Field(
        description="Name of the quality gate being evaluated (GateNameEnum value)."
    )
    passed: bool = Field(description="Whether the gate check passed.")
    rejection_reason: Optional[str] = Field(
        default=None,
        description="Explanation of why the gate failed. None if the gate passed.",
    )


class JudgeValidationReport(BaseModel):
    """Wraps a ReconciliationReport with 6 explicit gate-check results.

    The gate checks allow the PromptOptimizer to pinpoint exactly which quality
    dimension triggered a failure and generate targeted prompt adjustment deltas.

    Attributes:
        reconciliation_report: The ReconciliationReport produced by LayerTwoArbitrator.
        gate_checks:           Exactly 6 GateCheckResult objects (one per GateNameEnum).
        overall_passed:        True only if all 6 gate checks passed.
    """

    reconciliation_report: ReconciliationReport = Field(
        description="The ReconciliationReport produced by the LayerTwoArbitrator."
    )
    gate_checks: List[GateCheckResult] = Field(
        description="Exactly 6 gate check results evaluated against the ReconciliationReport."
    )
    overall_passed: bool = Field(
        description="True only if all 6 gate checks passed."
    )


def evaluate_reconciliation_report(
    report: ReconciliationReport,
) -> JudgeValidationReport:
    """Evaluate a ReconciliationReport against the 6 quality gates.

    This is the authoritative factory function for JudgeValidationReport.
    All gate evaluations are deterministic — given the same report, this
    function always returns the same JudgeValidationReport.

    Gates evaluated (in order):
        1. APPROVAL_GATE:               ready_for_approval must be True.
        2. DELIVERY_CONFIDENCE:         delivery_confidence_score >= 60.
        3. CONFLICT_SEVERITY_CONTROL:   No DimensionConflict with severity='Critical'.
        4. CONFLICT_COUNT_BOUNDED:      len(critical_conflicts) <= 3.
        5. RECOMMENDATIONS_PRESENT:     len(actionable_recommendations) >= 1.
        6. EXECUTIVE_SUMMARY_SUBSTANTIVE: len(executive_summary) >= 50.

    Args:
        report: A validated ReconciliationReport from LayerTwoArbitrator.

    Returns:
        JudgeValidationReport with all 6 gates evaluated and overall_passed set.
    """
    gate_checks: List[GateCheckResult] = []

    # Gate 1: APPROVAL_GATE
    if report.ready_for_approval:
        gate_checks.append(
            GateCheckResult(gate_name=GateNameEnum.APPROVAL_GATE, passed=True)
        )
    else:
        gate_checks.append(
            GateCheckResult(
                gate_name=GateNameEnum.APPROVAL_GATE,
                passed=False,
                rejection_reason=(
                    "ready_for_approval is False — proposal is not structurally sound to proceed."
                ),
            )
        )

    # Gate 2: DELIVERY_CONFIDENCE
    if report.delivery_confidence_score >= GATE_DELIVERY_CONFIDENCE_THRESHOLD:
        gate_checks.append(
            GateCheckResult(gate_name=GateNameEnum.DELIVERY_CONFIDENCE, passed=True)
        )
    else:
        gate_checks.append(
            GateCheckResult(
                gate_name=GateNameEnum.DELIVERY_CONFIDENCE,
                passed=False,
                rejection_reason=(
                    f"delivery_confidence_score={report.delivery_confidence_score} "
                    f"is below threshold of {GATE_DELIVERY_CONFIDENCE_THRESHOLD}."
                ),
            )
        )

    # Gate 3: CONFLICT_SEVERITY_CONTROL — no Critical-severity conflicts
    critical_severity = [
        c for c in report.critical_conflicts if c.severity.lower() == "critical"
    ]
    if not critical_severity:
        gate_checks.append(
            GateCheckResult(
                gate_name=GateNameEnum.CONFLICT_SEVERITY_CONTROL, passed=True
            )
        )
    else:
        names = ", ".join(
            "/".join(c.dimensions_involved) for c in critical_severity
        )
        gate_checks.append(
            GateCheckResult(
                gate_name=GateNameEnum.CONFLICT_SEVERITY_CONTROL,
                passed=False,
                rejection_reason=f"Critical-severity conflicts identified: {names}.",
            )
        )

    # Gate 4: CONFLICT_COUNT_BOUNDED
    conflict_count = len(report.critical_conflicts)
    if conflict_count <= GATE_MAX_CRITICAL_CONFLICTS:
        gate_checks.append(
            GateCheckResult(gate_name=GateNameEnum.CONFLICT_COUNT_BOUNDED, passed=True)
        )
    else:
        gate_checks.append(
            GateCheckResult(
                gate_name=GateNameEnum.CONFLICT_COUNT_BOUNDED,
                passed=False,
                rejection_reason=(
                    f"{conflict_count} conflicts identified; "
                    f"maximum is {GATE_MAX_CRITICAL_CONFLICTS}."
                ),
            )
        )

    # Gate 5: RECOMMENDATIONS_PRESENT
    if len(report.actionable_recommendations) >= 1:
        gate_checks.append(
            GateCheckResult(
                gate_name=GateNameEnum.RECOMMENDATIONS_PRESENT, passed=True
            )
        )
    else:
        gate_checks.append(
            GateCheckResult(
                gate_name=GateNameEnum.RECOMMENDATIONS_PRESENT,
                passed=False,
                rejection_reason="No actionable recommendations were produced.",
            )
        )

    # Gate 6: EXECUTIVE_SUMMARY_SUBSTANTIVE
    summary_len = len(report.executive_summary)
    if summary_len >= GATE_EXECUTIVE_SUMMARY_MIN_LENGTH:
        gate_checks.append(
            GateCheckResult(
                gate_name=GateNameEnum.EXECUTIVE_SUMMARY_SUBSTANTIVE, passed=True
            )
        )
    else:
        gate_checks.append(
            GateCheckResult(
                gate_name=GateNameEnum.EXECUTIVE_SUMMARY_SUBSTANTIVE,
                passed=False,
                rejection_reason=(
                    f"executive_summary length {summary_len} is below "
                    f"minimum of {GATE_EXECUTIVE_SUMMARY_MIN_LENGTH} characters."
                ),
            )
        )

    overall_passed = all(g.passed for g in gate_checks)
    return JudgeValidationReport(
        reconciliation_report=report,
        gate_checks=gate_checks,
        overall_passed=overall_passed,
    )
