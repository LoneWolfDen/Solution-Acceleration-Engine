"""
contexta/db/models.py — Python dataclasses mirroring SQLite row shapes.

These dataclasses are the return types of all repository functions.  They are
deliberately kept as plain dataclasses (not Pydantic models) to make the
boundary explicit: data coming *out* of the DB is in these shapes; data going
*into* the DB is validated through Pydantic models in repositories.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProjectRow:
    """Mirrors one row of the projects table."""

    id:          str
    name:        str
    global_tags: List[str] = field(default_factory=list)  # deserialised from JSON


@dataclass
class NodeRow:
    """
    Mirrors one row of the nodes table.

    content_markdown contains the serialised ReviewNodePayload JSON written by
    write_node().  Callers that need structured access should re-parse via
    ReviewNodePayload.model_validate_json(row.content_markdown).
    """

    id:               str
    project_id:       str
    parent_id:        Optional[str]
    layer_type:       str
    node_name:        str
    metadata_json:    Any                # raw JSON string (from DB reads) or dict (from direct construction)
    content_markdown: str               # raw JSON string from LLM / payload
    created_at:       str               # ISO-8601 UTC
    version_tag:      Optional[str] = None


@dataclass
class BlueprintRow:
    """Mirrors one row of the prompt_blueprints table."""

    id:                 str
    blueprint_name:     str
    version_string:     str
    master_prompt_text: str
    is_active:          bool


@dataclass
class InsightRow:
    """Mirrors one row of the global_client_insights table."""

    id:                     str
    client_or_industry_tag: str
    observed_pattern:       str
    frequency_count:        int
    last_updated:           str   # ISO-8601 UTC
