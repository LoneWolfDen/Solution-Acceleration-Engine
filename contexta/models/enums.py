"""Pydantic enums for the Contexta domain model.

All enums use `str` as a mixin so that Pydantic can coerce plain string
values returned by LLM responses without requiring strict mode.
"""

from enum import Enum

class ConfidenceEnum(str, Enum):
    RED = "RED"
    AMBER = "AMBER"
    GREEN = "GREEN"

class CitationTypeEnum(str, Enum):
    DIRECT_REFERENCE = "Direct Reference"
    ADVISED_IN_RELATION = "Advised in Relation"

class ReviewDimensionEnum(str, Enum):
    INTENT = "Intent"
    SCOPE = "Scope"
    OWNERSHIP = "Ownership"
    DELIVERY = "Delivery"
    TIMELINE = "Timeline"
    ARCHITECTURE = "Architecture"
    NFR = "NFR"
    RESOURCE = "Resource"
    RISK = "Risk"
    COMMERCIAL = "Commercial"
    LANGUAGE = "Language"
    CONSISTENCY = "Consistency"

class MitigationRoutingEnum(str, Enum):
    SCOPE_MODIFICATION = "Scope Modification"
    RISK_REGISTER = "Risk Register"
    ASSUMPTIONS_MATRIX = "Assumptions Matrix"
    BOTH_R_AND_A = "Both R&A"
    IGNORED = "Ignored"


class PhaseEnum(str, Enum):
    """Pipeline execution phases used to categorise KnowledgeMemory observations."""

    DIMENSION_REVIEW = "DIMENSION_REVIEW"
    ARBITRATION = "ARBITRATION"
    LAYER_TWO_SYNTHESIS = "LAYER_TWO_SYNTHESIS"
    ADVISORY = "ADVISORY"
