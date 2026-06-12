"""
contexta/models/export.py — JSON export / import schema models.

JSONPacket is the top-level model for the flat JSON export produced by the
[E] Export action.  It is self-describing via schema_version so that future
Contexta versions can detect and handle legacy packets during import.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .payloads import ReviewNodePayload

EXPORT_SCHEMA_VERSION = "1.0"


class ExportArbitratorResult(BaseModel):
    """
    Serialised output from the Layer 2 Arbitrator Persona.

    Stored inside JSONPacket.arbitrator_result when a Compare run has been
    completed.  The contradictions list contains raw dicts as returned by the
    LLM (each with keys: dimension_a, dimension_b, description).
    """

    contradictions: List[Dict[str, Any]]
    raw_llm_response: str


class JSONPacket(BaseModel):
    """
    Flat, portable JSON representation of the full pipeline state for one node.

    Schema is intentionally flat (no deeply nested sub-objects beyond the
    existing Pydantic models) so that external tooling can consume it without
    requiring Contexta as a dependency.

    Attributes:
        schema_version:     Contexta export schema version string.  Always
                            present; used during import validation.
        project_id:         UUID of the source project.
        project_name:       Human-readable project name.
        global_tags:        Project-level tag list.
        node_id:            UUID of the exported node.
        node_name:          Human-readable node name.
        parent_node_id:     UUID of the parent node, if this is a fork.
        layer_type:         'exploration' or 'synthesis'.
        created_at:         ISO-8601 UTC timestamp of node creation.
        payloads:           All 12 ReviewNodePayload objects (Layer 1 output).
        arbitrator_result:  Layer 2 Arbitrator output, if present.
        routing_decisions:  Governance routing decisions recorded in metadata.
        metadata:           Raw metadata_json dict for any remaining fields.
        version_tag:        Optional human-assigned version label for the node.
    """

    schema_version:    str = Field(default=EXPORT_SCHEMA_VERSION)
    project_id:        str
    project_name:      str
    global_tags:       List[str]
    node_id:           str
    node_name:         str
    parent_node_id:    Optional[str] = None
    layer_type:        str
    created_at:        str
    payloads:          List[ReviewNodePayload]
    arbitrator_result: Optional[ExportArbitratorResult] = None
    routing_decisions: List[Dict[str, Any]] = Field(default_factory=list)
    metadata:          Dict[str, Any] = Field(default_factory=dict)
    version_tag:       Optional[str] = None
