"""Python dataclasses mirroring SQLite row shapes.

These are plain data containers used to ferry row data out of
``db/repositories.py`` without coupling callers to raw tuple indexing.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ProjectRow:
    id: str
    name: str
    global_tags: List[str]


@dataclass
class NodeRow:
    id: str
    project_id: str
    parent_id: Optional[str]
    layer_type: str
    node_name: str
    metadata_json: str
    content_markdown: str
    created_at: str


@dataclass
class BlueprintRow:
    id: str
    blueprint_name: str
    version_string: str
    master_prompt_text: str
    is_active: bool


@dataclass
class InsightRow:
    id: str
    client_or_industry_tag: str
    observed_pattern: str
    frequency_count: int
    last_updated: str
