"""Layer 2 synthesis data contracts.

Defines the Pydantic models for the ReconciliationReport produced by the
LayerTwoArbitrator synthesis pipeline.  These models are the authoritative
schema for Layer 2 output — they are used for LLM response validation, DB
persistence (via metadata_json), and export serialisation.
"""

from __future__ import annotations

from typing import List

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
