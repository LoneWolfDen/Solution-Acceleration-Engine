"""Export schema — JSONPacket and ExportArbitratorResult Pydantic models.

``EXPORT_SCHEMA_VERSION`` is embedded in every exported packet so that
deserializers can detect schema drift between Contexta releases.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel

from .payloads import ReviewNodePayload

EXPORT_SCHEMA_VERSION = "1.0"


class ExportArbitratorResult(BaseModel):
    contradictions: List[Dict]
    raw_llm_response: str


class JSONPacket(BaseModel):
    schema_version: str = EXPORT_SCHEMA_VERSION
    export_timestamp: str  # ISO-8601 UTC
    project_name: str
    project_global_tags: List[str]
    node_id: str
    node_name: str
    parent_node_id: Optional[str] = None
    layer_type: str
    dimension_payloads: List[ReviewNodePayload]
    arbitrator_result: Optional[ExportArbitratorResult] = None
    routing_decisions: List[Dict]
    metadata: Dict
    created_at: str  # ISO-8601 UTC
