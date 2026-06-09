"""
contexta/models/enums.py — All domain enumerations.

These are str-enums so they serialise naturally to their string value in both
JSON and SQLite without any custom encoder.  Pydantic v2 coerces matching
string literals to enum members automatically (strict=False default).
"""

from __future__ import annotations

from enum import Enum


class ConfidenceEnum(str, Enum):
    """Risk confidence level emitted by an LLM dimension review."""

    RED   = "RED"
    AMBER = "AMBER"
    GREEN = "GREEN"


class CitationTypeEnum(str, Enum):
    """Classifies how a SourceCitation relates to the finding."""

    DIRECT_REFERENCE    = "Direct Reference"
    ADVISED_IN_RELATION = "Advised in Relation"


class ReviewDimensionEnum(str, Enum):
    """
    The 12 independent review axes.  Exactly 12 values — do not add or remove
    members without updating the dimension task orchestrator and TUI row factory.
    """

    INTENT       = "Intent"
    SCOPE        = "Scope"
    OWNERSHIP    = "Ownership"
    DELIVERY     = "Delivery"
    TIMELINE     = "Timeline"
    ARCHITECTURE = "Architecture"
    NFR          = "NFR"
    RESOURCE     = "Resource"
    RISK         = "Risk"
    COMMERCIAL   = "Commercial"
    LANGUAGE     = "Language"
    CONSISTENCY  = "Consistency"


class MitigationRoutingEnum(str, Enum):
    """Routing decision applied to an IssueFinding during governance review."""

    SCOPE_MODIFICATION = "Scope Modification"
    RISK_REGISTER      = "Risk Register"
    ASSUMPTIONS_MATRIX = "Assumptions Matrix"
    BOTH_R_AND_A       = "Both R&A"
    IGNORED            = "Ignored"
