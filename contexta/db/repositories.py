"""
contexta/db/repositories.py — All async SQL read/write functions.

Design rules enforced here:
  - This is the ONLY file that contains raw SQL in the project.
  - Every node write re-validates the payload against ReviewNodePayload.
  - activate_blueprint() uses an explicit BEGIN / COMMIT transaction to
    guarantee the one-active invariant atomically.
  - No unvalidated dicts cross the public function boundaries.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite
from pydantic import ValidationError

from ..models.payloads import ReviewNodePayload
from .models import (
    BlueprintRow,
    InsightRow,
    IntelligenceRow,
    NodeRow,
    ObservationRow,
    ProjectRow,
    ReviewRow,
    VersionRow,
)
from .models import BlueprintRow, InsightRow, NodeRow, ProjectRow, VersionRow, ObservationRow, ReviewRow


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _row_to_project(row: aiosqlite.Row) -> ProjectRow:
    return ProjectRow(
        id=row["id"],
        name=row["name"],
        global_tags=json.loads(row["global_tags"] or "[]"),
    )


def _row_to_version(row: aiosqlite.Row) -> VersionRow:
    return VersionRow(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        description=row["description"],
        created_at=row["created_at"],
    )


def _row_to_node(row: aiosqlite.Row) -> NodeRow:
    return NodeRow(
        id=row["id"],
        project_id=row["project_id"],
        parent_id=row["parent_id"],
        layer_type=row["layer_type"],
        node_name=row["node_name"],
        # Keep as raw JSON string so callers can decide whether to parse.
        # Tests that use get_node / list_nodes_for_project expect a
        # json.loads()-able string; fork_node / write_node return dict directly.
        metadata_json=row["metadata_json"] or "{}",
        content_markdown=row["content_markdown"] or "",
        created_at=row["created_at"],
        version_tag=row["version_tag"],
        version_id=row["version_id"],
    )


def _row_to_blueprint(row: aiosqlite.Row) -> BlueprintRow:
    return BlueprintRow(
        id=row["id"],
        blueprint_name=row["blueprint_name"],
        version_string=row["version_string"],
        master_prompt_text=row["master_prompt_text"],
        is_active=bool(row["is_active"]),
    )


def _row_to_insight(row: aiosqlite.Row) -> InsightRow:
    return InsightRow(
        id=row["id"],
        client_or_industry_tag=row["client_or_industry_tag"],
        observed_pattern=row["observed_pattern"],
        frequency_count=row["frequency_count"],
        last_updated=row["last_updated"],
    )


def _row_to_review(row: aiosqlite.Row) -> ReviewRow:
    return ReviewRow(
        id=row["id"],
        version_id=row["version_id"],
        persona_prompt=row["persona_prompt"],
        user_context_text=row["user_context_text"],
        sme_augmentation_list=json.loads(row["sme_augmentation_list"] or "[]"),
        dimension_output=json.loads(row["dimension_output"] or "[]"),
        created_at=row["created_at"],
    )


def _row_to_observation(row: aiosqlite.Row) -> ObservationRow:
    return ObservationRow(
        id=row["id"],
        phase=row["phase"],
        node_id=row["node_id"],
        dimension=row["dimension"],
        base_value=row["base_value"],
        amended_value=row["amended_value"],
        rationale=row["rationale"],
        timestamp=row["timestamp"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────

async def create_project(
    conn: aiosqlite.Connection,
    name: str,
    global_tags: List[str],
) -> ProjectRow:
    """Insert a new project row and return it."""
    row_id = _new_id()
    await conn.execute(
        "INSERT INTO projects (id, name, global_tags) VALUES (?, ?, ?)",
        (row_id, name, json.dumps(global_tags)),
    )
    await conn.commit()
    return ProjectRow(id=row_id, name=name, global_tags=global_tags)


async def get_project(
    conn: aiosqlite.Connection,
    project_id: str,
) -> Optional[ProjectRow]:
    """Return the project with the given id, or None if not found."""
    cursor = await conn.execute(
        "SELECT id, name, global_tags FROM projects WHERE id = ?",
        (project_id,),
    )
    row = await cursor.fetchone()
    return _row_to_project(row) if row else None


async def list_projects(conn: aiosqlite.Connection) -> List[ProjectRow]:
    """Return all projects ordered by rowid (insertion order)."""
    cursor = await conn.execute("SELECT id, name, global_tags FROM projects ORDER BY rowid")
    rows = await cursor.fetchall()
    return [_row_to_project(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Versions
# ─────────────────────────────────────────────────────────────────────────────

async def create_version(
    conn: aiosqlite.Connection,
    project_id: str,
    name: str,
    description: Optional[str] = None,
) -> VersionRow:
    """Insert a new version row and return it.

    A Version groups one or more nodes under a named iteration within a
    Project.  Multiple Versions under a Project enable cross-version
    comparison (scope.md — Comparison module, status PENDING).

    Args:
        conn:        Open aiosqlite connection.
        project_id:  FK → projects.id.
        name:        Human-readable version label, e.g. "v1.0 — Initial Review".
        description: Optional free-text notes about this version.

    Returns:
        ``VersionRow`` representing the newly inserted row.
    """
    row_id = _new_id()
    now = _now_iso()
    await conn.execute(
        "INSERT INTO versions (id, project_id, name, description, created_at) VALUES (?, ?, ?, ?, ?)",
        (row_id, project_id, name, description, now),
    )
    await conn.commit()
    return VersionRow(
        id=row_id,
        project_id=project_id,
        name=name,
        description=description,
        created_at=now,
    )


async def get_version(
    conn: aiosqlite.Connection,
    version_id: str,
) -> Optional[VersionRow]:
    """Return the version with the given id, or None if not found."""
    cursor = await conn.execute(
        "SELECT id, project_id, name, description, created_at FROM versions WHERE id = ?",
        (version_id,),
    )
    row = await cursor.fetchone()
    return _row_to_version(row) if row else None


async def list_versions_for_project(
    conn: aiosqlite.Connection,
    project_id: str,
) -> List[VersionRow]:
    """Return all versions for a project ordered by creation time."""
    cursor = await conn.execute(
        "SELECT id, project_id, name, description, created_at "
        "FROM versions WHERE project_id = ? ORDER BY created_at",
        (project_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_version(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Nodes
# ─────────────────────────────────────────────────────────────────────────────

async def write_node(
    conn: aiosqlite.Connection,
    project_id: str,
    parent_id: Optional[str],
    layer_type: str,
    node_name: str,
    payload: ReviewNodePayload,
    metadata: dict,
    version_tag: Optional[str] = None,
    version_id: Optional[str] = None,
) -> NodeRow:
    """
    Validate *payload* against ReviewNodePayload, then write a nodes row.

    The Pydantic re-validation guard (model_validate on the serialised form)
    ensures that even a mutated in-memory payload object cannot bypass the
    schema contract.  If validation fails, ValidationError is raised and NO
    database write occurs.

    Args:
        conn:        Open aiosqlite connection.
        project_id:  FK → projects.id.
        parent_id:   FK → nodes.id for fork lineage; None for root nodes.
        layer_type:  'exploration' or 'synthesis'.
        node_name:   Human-readable name for this node.
        payload:     ReviewNodePayload to persist.
        metadata:    Arbitrary metadata dict stored as JSON.
        version_tag: Optional legacy human-assigned version label string.
        version_id:  Optional FK → versions.id — the Version this node belongs to.

    Returns:
        NodeRow representing the newly inserted row.

    Raises:
        ValidationError: if *payload* fails the re-validation gate.
    """
    # Pydantic re-validation guard — serialise then re-parse to catch mutations.
    validated: ReviewNodePayload = ReviewNodePayload.model_validate(
        json.loads(payload.model_dump_json())
    )

    row_id = _new_id()
    now = _now_iso()
    content_markdown = validated.model_dump_json()

    await conn.execute(
        """
        INSERT INTO nodes
            (id, project_id, parent_id, layer_type, node_name,
             metadata_json, content_markdown, created_at, version_tag, version_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            project_id,
            parent_id,
            layer_type,
            node_name,
            json.dumps(metadata),
            content_markdown,
            now,
            version_tag,
            version_id,
        ),
    )
    await conn.commit()

    return NodeRow(
        id=row_id,
        project_id=project_id,
        parent_id=parent_id,
        layer_type=layer_type,
        node_name=node_name,
        metadata_json=metadata,
        content_markdown=content_markdown,
        created_at=now,
        version_tag=version_tag,
        version_id=version_id,
    )


async def get_node(
    conn: aiosqlite.Connection,
    node_id: str,
) -> Optional[NodeRow]:
    """Return the node with the given id, or None."""
    cursor = await conn.execute(
        """
        SELECT id, project_id, parent_id, layer_type, node_name,
               metadata_json, content_markdown, created_at, version_tag, version_id
        FROM nodes WHERE id = ?
        """,
        (node_id,),
    )
    row = await cursor.fetchone()
    return _row_to_node(row) if row else None


async def list_nodes_for_project(
    conn: aiosqlite.Connection,
    project_id: str,
) -> List[NodeRow]:
    """Return all nodes for a project ordered by creation time."""
    cursor = await conn.execute(
        """
        SELECT id, project_id, parent_id, layer_type, node_name,
               metadata_json, content_markdown, created_at, version_tag, version_id
        FROM nodes WHERE project_id = ? ORDER BY created_at
        """,
        (project_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_node(r) for r in rows]


async def list_all_nodes(conn: aiosqlite.Connection) -> List[NodeRow]:
    """Return every node across all projects (used by DreamCycleWorker)."""
    cursor = await conn.execute(
        """
        SELECT id, project_id, parent_id, layer_type, node_name,
               metadata_json, content_markdown, created_at, version_tag, version_id
        FROM nodes ORDER BY created_at
        """
    )
    rows = await cursor.fetchall()
    return [_row_to_node(r) for r in rows]


async def fork_node(
    conn: aiosqlite.Connection,
    parent_node_id: str,
    new_node_name: str,
    version_tag: Optional[str] = None,
    version_id: Optional[str] = None,
) -> NodeRow:
    """
    Create a new node branched from an existing node.

    The fork inherits ``project_id``, ``layer_type``, and ``version_id`` from
    the parent.  If *version_id* is explicitly provided it overrides the
    inherited value — this allows callers to place the fork into a different
    version when needed.  ``content_markdown`` and ``metadata_json`` start
    empty: the fork represents a fresh review state, not a copy of the
    parent's findings.

    Args:
        conn:           Open aiosqlite connection.
        parent_node_id: id of the node to branch from.
        new_node_name:  Name for the forked node.
        version_tag:    Optional legacy version label string.
        version_id:     Optional FK → versions.id.  When omitted, the
                        parent's ``version_id`` is inherited automatically
                        (satisfies Gap 3 Property 6 requirement).

    Returns:
        The newly created NodeRow.

    Raises:
        ValueError: if parent_node_id does not exist.
    """
    parent = await get_node(conn, parent_node_id)
    if parent is None:
        raise ValueError(f"Parent node '{parent_node_id}' not found.")

    # Inherit version_id from parent when not explicitly overridden by caller.
    effective_version_id = version_id if version_id is not None else parent.version_id

    row_id = _new_id()
    now = _now_iso()

    await conn.execute(
        """
        INSERT INTO nodes
            (id, project_id, parent_id, layer_type, node_name,
             metadata_json, content_markdown, created_at, version_tag, version_id)
        VALUES (?, ?, ?, ?, ?, '{}', '', ?, ?, ?)
        """,
        (
            row_id,
            parent.project_id,
            parent_node_id,
            parent.layer_type,
            new_node_name,
            now,
            version_tag,
            effective_version_id,
        ),
    )
    await conn.commit()

    return NodeRow(
        id=row_id,
        project_id=parent.project_id,
        parent_id=parent_node_id,
        layer_type=parent.layer_type,
        node_name=new_node_name,
        metadata_json={},
        content_markdown="",
        created_at=now,
        version_tag=version_tag,
        version_id=effective_version_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Prompt Blueprints
# ─────────────────────────────────────────────────────────────────────────────

async def get_active_blueprint(
    conn: aiosqlite.Connection,
) -> Optional[BlueprintRow]:
    """Return the currently active blueprint, or None if none is active."""
    cursor = await conn.execute(
        """
        SELECT id, blueprint_name, version_string, master_prompt_text, is_active
        FROM prompt_blueprints WHERE is_active = 1 LIMIT 1
        """
    )
    row = await cursor.fetchone()
    return _row_to_blueprint(row) if row else None


async def activate_blueprint(
    conn: aiosqlite.Connection,
    blueprint_id: str,
) -> None:
    """
    Set is_active=1 for *blueprint_id* and is_active=0 for all others.

    The two UPDATE statements are wrapped in an explicit BEGIN/COMMIT
    transaction to guarantee the one-active invariant holds even under
    concurrent access.  At no point in time can more than one blueprint
    row have is_active=1.

    Args:
        conn:         Open aiosqlite connection.
        blueprint_id: id of the blueprint to activate.

    Raises:
        ValueError: if *blueprint_id* does not exist.
    """
    # Verify the target row exists before touching anything.
    cursor = await conn.execute(
        "SELECT id FROM prompt_blueprints WHERE id = ?", (blueprint_id,)
    )
    if await cursor.fetchone() is None:
        raise ValueError(f"Blueprint '{blueprint_id}' not found.")

    # Atomic swap: clear all → set one.
    await conn.execute("BEGIN")
    try:
        await conn.execute("UPDATE prompt_blueprints SET is_active = 0")
        await conn.execute(
            "UPDATE prompt_blueprints SET is_active = 1 WHERE id = ?",
            (blueprint_id,),
        )
        await conn.execute("COMMIT")
    except Exception:
        await conn.execute("ROLLBACK")
        raise


async def save_blueprint_version(
    conn: aiosqlite.Connection,
    name: str,
    version: str,
    prompt_text: str,
) -> BlueprintRow:
    """
    Insert a new prompt blueprint row without modifying any existing row.

    New rows are always inactive (is_active=0).  Call activate_blueprint()
    separately to make a version live.
    """
    row_id = _new_id()
    await conn.execute(
        """
        INSERT INTO prompt_blueprints
            (id, blueprint_name, version_string, master_prompt_text, is_active)
        VALUES (?, ?, ?, ?, 0)
        """,
        (row_id, name, version, prompt_text),
    )
    await conn.commit()
    return BlueprintRow(
        id=row_id,
        blueprint_name=name,
        version_string=version,
        master_prompt_text=prompt_text,
        is_active=False,
    )


async def list_blueprints(conn: aiosqlite.Connection) -> List[BlueprintRow]:
    """Return all blueprints ordered by rowid (insertion order)."""
    cursor = await conn.execute(
        """
        SELECT id, blueprint_name, version_string, master_prompt_text, is_active
        FROM prompt_blueprints ORDER BY rowid
        """
    )
    rows = await cursor.fetchall()
    return [_row_to_blueprint(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Global Client Insights
# ─────────────────────────────────────────────────────────────────────────────

async def upsert_insight(
    conn: aiosqlite.Connection,
    client_tag: str,
    pattern: str,
) -> InsightRow:
    """
    Increment frequency_count for an existing (client_tag, pattern) pair, or
    insert a new row with frequency_count=1 if the pair is novel.
    """
    now = _now_iso()
    row_id = _new_id()

    await conn.execute(
        """
        INSERT INTO global_client_insights
            (id, client_or_industry_tag, observed_pattern, frequency_count, last_updated)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(client_or_industry_tag, observed_pattern)
        DO UPDATE SET
            frequency_count = frequency_count + 1,
            last_updated    = excluded.last_updated
        """,
        (row_id, client_tag, pattern, now),
    )
    await conn.commit()

    # Re-fetch to get the current state (id and frequency_count may differ
    # from what we inserted if the row already existed).
    cursor = await conn.execute(
        """
        SELECT id, client_or_industry_tag, observed_pattern,
               frequency_count, last_updated
        FROM global_client_insights
        WHERE client_or_industry_tag = ? AND observed_pattern = ?
        """,
        (client_tag, pattern),
    )
    row = await cursor.fetchone()
    return _row_to_insight(row)  # type: ignore[arg-type]


async def get_insights_for_tags(
    conn: aiosqlite.Connection,
    tags: List[str],
) -> List[InsightRow]:
    """
    Return all insight rows whose client_or_industry_tag matches any value in
    *tags*.  Uses a parameterised IN clause built at call time.
    """
    if not tags:
        return []

    placeholders = ",".join("?" * len(tags))
    cursor = await conn.execute(
        f"""
        SELECT id, client_or_industry_tag, observed_pattern,
               frequency_count, last_updated
        FROM global_client_insights
        WHERE client_or_industry_tag IN ({placeholders})
        ORDER BY frequency_count DESC
        """,
        tuple(tags),
    )
    rows = await cursor.fetchall()
    return [_row_to_insight(r) for r in rows]



# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — Synthesis nodes
# ─────────────────────────────────────────────────────────────────────────────

#: Key used inside ``metadata_json`` to store the ``ReconciliationReport`` dict.
_RECONCILIATION_REPORT_KEY = "reconciliation_report"


async def write_synthesis_node(
    conn: aiosqlite.Connection,
    project_id: str,
    parent_id: Optional[str],
    node_name: str,
    report: "ReconciliationReport",  # type: ignore[name-defined]
    version_tag: Optional[str] = None,
    version_id: Optional[str] = None,
) -> NodeRow:
    """Persist a Layer 2 ``ReconciliationReport`` as a synthesis node.

    The report is stored in two forms:
    - ``content_markdown`` — the raw ``model_dump_json()`` string for direct
      retrieval and export.
    - ``metadata_json[_RECONCILIATION_REPORT_KEY]`` — the parsed dict so that
      callers can read individual fields without a full Pydantic round-trip.

    No schema migration is required: the data lives entirely within the
    existing ``metadata_json`` TEXT column.

    Args:
        conn:        Open aiosqlite connection.
        project_id:  FK → projects.id.
        parent_id:   FK → nodes.id (the Layer 1 exploration node); None if root.
        node_name:   Human-readable label for this synthesis node.
        report:      Validated ``ReconciliationReport`` to persist.
        version_tag: Optional legacy version label string.
        version_id:  Optional FK → versions.id for the synthesis node.

    Returns:
        NodeRow representing the newly inserted row.
    """
    # Local import keeps repositories.py importable without llm.models loaded.
    from ..llm.models import ReconciliationReport

    # Re-validate to guard against mutated in-memory objects.
    validated: ReconciliationReport = ReconciliationReport.model_validate(
        json.loads(report.model_dump_json())
    )

    row_id = _new_id()
    now = _now_iso()
    content_markdown = validated.model_dump_json()
    metadata = {
        _RECONCILIATION_REPORT_KEY: validated.model_dump(),
        "completed_at": now,
    }

    await conn.execute(
        """
        INSERT INTO nodes
            (id, project_id, parent_id, layer_type, node_name,
             metadata_json, content_markdown, created_at, version_tag, version_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            project_id,
            parent_id,
            "synthesis",
            node_name,
            json.dumps(metadata),
            content_markdown,
            now,
            version_tag,
            version_id,
        ),
    )
    await conn.commit()

    return NodeRow(
        id=row_id,
        project_id=project_id,
        parent_id=parent_id,
        layer_type="synthesis",
        node_name=node_name,
        metadata_json=metadata,
        content_markdown=content_markdown,
        created_at=now,
        version_tag=version_tag,
        version_id=version_id,
    )


async def get_synthesis_report(
    conn: aiosqlite.Connection,
    node_id: str,
) -> "Optional[ReconciliationReport]":  # type: ignore[name-defined]
    """Return the ``ReconciliationReport`` stored in a synthesis node, or ``None``.

    Reads the node row, extracts ``metadata_json[_RECONCILIATION_REPORT_KEY]``,
    and re-validates through Pydantic before returning so the caller always
    receives a fully-typed object.

    Args:
        conn:    Open aiosqlite connection.
        node_id: id of the synthesis node to read.

    Returns:
        ``ReconciliationReport`` if the node exists and contains a valid report;
        ``None`` if the node does not exist or the key is absent.
    """
    from ..llm.models import ReconciliationReport

    node = await get_node(conn, node_id)
    if node is None:
        return None

    raw_meta = node.metadata_json
    metadata: dict = (
        json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    )

    report_data = metadata.get(_RECONCILIATION_REPORT_KEY)
    if report_data is None:
        return None

    return ReconciliationReport.model_validate(report_data)


# ─────────────────────────────────────────────────────────────────────────────
# Intelligence Layer  (Sprint 6)
# ─────────────────────────────────────────────────────────────────────────────


def _row_to_intelligence(row: aiosqlite.Row) -> IntelligenceRow:
    return IntelligenceRow(
        id=row["id"],
        project_id=row["project_id"],
        insight_type=row["insight_type"],
        source_node_id=row["source_node_id"],
        payload_json=row["payload_json"] or "{}",
        created_at=row["created_at"],
    )


async def write_intelligence_record(
    conn: aiosqlite.Connection,
    insight_type: str,
    payload: dict,
    project_id: Optional[str] = None,
    source_node_id: Optional[str] = None,
) -> IntelligenceRow:
    """Insert a new ``intelligence_layer`` record and return it.

    Args:
        conn:           Open aiosqlite connection.
        insight_type:   One of 'CITATION_TREND', 'CONFIDENCE_TREND', 'PROMPT_DELTA'.
        payload:        Dict to serialise as the ``payload_json`` column.
        project_id:     FK → projects.id.  None for global insights.
        source_node_id: FK → nodes.id.  None for multi-node aggregated insights.

    Returns:
        ``IntelligenceRow`` representing the newly inserted record.
    """
    row_id = _new_id()
    now = _now_iso()
    payload_json = json.dumps(payload)

    await conn.execute(
        """
        INSERT INTO intelligence_layer
            (id, project_id, insight_type, source_node_id, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (row_id, project_id, insight_type, source_node_id, payload_json, now),
    )
    await conn.commit()

    return IntelligenceRow(
        id=row_id,
        project_id=project_id,
        insight_type=insight_type,
        source_node_id=source_node_id,
        payload_json=payload_json,
        created_at=now,
    )


async def get_intelligence_for_project(
    conn: aiosqlite.Connection,
    project_id: str,
) -> List[IntelligenceRow]:
    """Return all intelligence records for *project_id*, ordered by creation time.

    Args:
        conn:       Open aiosqlite connection.
        project_id: FK → projects.id to filter on.

    Returns:
        List of ``IntelligenceRow`` objects, oldest first.  Empty list if none found.
    """
    cursor = await conn.execute(
        """
        SELECT id, project_id, insight_type, source_node_id, payload_json, created_at
        FROM intelligence_layer
        WHERE project_id = ?
        ORDER BY created_at
        """,
        (project_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_intelligence(r) for r in rows]


async def get_intelligence_global(
    conn: aiosqlite.Connection,
) -> List[IntelligenceRow]:
    """Return all intelligence records with ``project_id IS NULL`` (global insights).

    Args:
        conn: Open aiosqlite connection.

    Returns:
        List of ``IntelligenceRow`` objects, oldest first.  Empty list if none found.
    """
    cursor = await conn.execute(
        """
        SELECT id, project_id, insight_type, source_node_id, payload_json, created_at
        FROM intelligence_layer
        WHERE project_id IS NULL
        ORDER BY created_at
        """
    )
    rows = await cursor.fetchall()
    return [_row_to_intelligence(r) for r in rows]


async def get_intelligence_by_type(
    conn: aiosqlite.Connection,
    insight_type: str,
    project_id: Optional[str] = None,
) -> List[IntelligenceRow]:
    """Return intelligence records filtered by *insight_type*, optionally scoped to a project.

    When *project_id* is provided, only records for that project are returned.
    When *project_id* is ``None``, all records of the given type are returned
    regardless of project scope (including global records).

    Args:
        conn:         Open aiosqlite connection.
        insight_type: One of 'CITATION_TREND', 'CONFIDENCE_TREND', 'PROMPT_DELTA'.
        project_id:   Optional FK → projects.id.  None = return all matching types.

    Returns:
        List of ``IntelligenceRow`` objects, oldest first.
    """
    if project_id is not None:
        cursor = await conn.execute(
            """
            SELECT id, project_id, insight_type, source_node_id, payload_json, created_at
            FROM intelligence_layer
            WHERE insight_type = ? AND project_id = ?
            ORDER BY created_at
            """,
            (insight_type, project_id),
        )
    else:
        cursor = await conn.execute(
            """
            SELECT id, project_id, insight_type, source_node_id, payload_json, created_at
            FROM intelligence_layer
            WHERE insight_type = ?
            ORDER BY created_at
            """,
            (insight_type,),
        )
    rows = await cursor.fetchall()
    return [_row_to_intelligence(r) for r in rows]



# ─────────────────────────────────────────────────────────────────────────────
# Reviews
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_review(row: aiosqlite.Row) -> ReviewRow:
    return ReviewRow(
        id=row["id"],
        version_id=row["version_id"],
        persona_prompt=row["persona_prompt"],
        user_context_text=row["user_context_text"],
        sme_augmentation_list=json.loads(row["sme_augmentation_list"] or "[]"),
        dimension_output=json.loads(row["dimension_output"] or "[]"),
        created_at=row["created_at"],
    )


async def create_review(
    conn: aiosqlite.Connection,
    version_id: str,
    persona_prompt: str,
    user_context_text: str,
    sme_augmentation_list: List[str],
    dimension_output: List[dict],
) -> ReviewRow:
    """Insert a new review row and return it.

    A Review records a single arbitration run scoped to a Version.  The
    ``version_id`` is mandatory — it is the provenance anchor that satisfies
    the Traceability Standard (scope.md §3): every ReviewRow must be linked
    to exactly one Version.

    Args:
        conn:                  Open aiosqlite connection.
        version_id:            FK → versions.id.
        persona_prompt:        The LLM persona prompt used for this run.
        user_context_text:     Free-text user-supplied context or briefing.
        sme_augmentation_list: List of SME knowledge augmentation strings.
        dimension_output:      List of dicts for the 12-dimension review output.
        conn:                 Open aiosqlite connection.
        version_id:           FK → versions.id.  Must reference an existing
                              version; the FK constraint is enforced by SQLite.
        persona_prompt:       The LLM persona prompt used for this run.
        user_context_text:    Free-text user-supplied context or briefing.
        sme_augmentation_list: List of SME knowledge augmentation strings;
                              serialised to a JSON array in the DB.
        dimension_output:     List of dicts representing the 12-dimension
                              review output; serialised to a JSON array in the
                              DB (maps to the spec's ``12_dimension_output``
                              field).

    Returns:
        ``ReviewRow`` representing the newly inserted row.
    """
    row_id = _new_id()
    now = _now_iso()

    await conn.execute(
        """
        INSERT INTO reviews
            (id, version_id, persona_prompt, user_context_text,
             sme_augmentation_list, dimension_output, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            version_id,
            persona_prompt,
            user_context_text,
            json.dumps(sme_augmentation_list),
            json.dumps(dimension_output),
            now,
        ),
    )
    await conn.commit()

    return ReviewRow(
        id=row_id,
        version_id=version_id,
        persona_prompt=persona_prompt,
        user_context_text=user_context_text,
        sme_augmentation_list=sme_augmentation_list,
        dimension_output=dimension_output,
        created_at=now,
    )


async def get_review(
    conn: aiosqlite.Connection,
    review_id: str,
) -> Optional[ReviewRow]:
    """Return the review with the given id, or None if not found.

    Args:
        conn:      Open aiosqlite connection.
        review_id: UUID primary key of the review row to fetch.

    Returns:
        ``ReviewRow`` if found; ``None`` otherwise.
    """
    cursor = await conn.execute(
        """
        SELECT id, version_id, persona_prompt, user_context_text,
               sme_augmentation_list, dimension_output, created_at
        FROM reviews WHERE id = ?
        """,
        (review_id,),
    )
    row = await cursor.fetchone()
    return _row_to_review(row) if row else None


async def list_reviews_for_version(
    conn: aiosqlite.Connection,
    version_id: str,
) -> List[ReviewRow]:
    """Return all reviews for a version ordered by creation time.

    Args:
        conn:       Open aiosqlite connection.
        version_id: FK → versions.id — the Version whose reviews to list.

    Returns:
        List of ``ReviewRow`` objects, oldest first.  Empty list if the
        version has no reviews.
    """
    cursor = await conn.execute(
        """
        SELECT id, version_id, persona_prompt, user_context_text,
               sme_augmentation_list, dimension_output, created_at
        FROM reviews WHERE version_id = ? ORDER BY created_at
        """,
        (version_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_review(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Observations
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_observation(row: aiosqlite.Row) -> ObservationRow:
    return ObservationRow(
        id=row["id"],
        phase=row["phase"],
        node_id=row["node_id"],
        dimension=row["dimension"],
        base_value=row["base_value"],
        amended_value=row["amended_value"],
        rationale=row["rationale"],
        timestamp=row["timestamp"],
    )

# Knowledge Observations
# ─────────────────────────────────────────────────────────────────────────────


async def write_observation(
    conn: aiosqlite.Connection,
    phase: str,
    node_id: str,
    dimension: str,
    base_value: str,
    amended_value: str,
    rationale: str,
) -> ObservationRow:
    """Persist a single user annotation as a KnowledgeMemory observation.

    Args:
        conn:          Open aiosqlite connection.
        phase:         PhaseEnum.value — pipeline phase of the source finding.
        node_id:       Logical context key (exploration node id or session id).
        dimension:     ReviewDimensionEnum.value the finding belongs to.
        base_value:    Original AI-produced text at annotation time.
        amended_value: User's override text.
        rationale:     Why the user made this change.

    Returns:
        ObservationRow representing the newly inserted row.
    """
    row_id = _new_id()
    now = _now_iso()
    await conn.execute(
        """
        INSERT INTO knowledge_observations
            (id, phase, node_id, dimension, base_value, amended_value, rationale, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (row_id, phase, node_id, dimension, base_value, amended_value, rationale, now),
    )
    await conn.commit()
    return ObservationRow(
        id=row_id,
        phase=phase,
        node_id=node_id,
        dimension=dimension,
        base_value=base_value,
        amended_value=amended_value,
        rationale=rationale,
        timestamp=now,
    )


async def get_observations_for_context(
    conn: aiosqlite.Connection,
    dimension: Optional[str] = None,
    phase: Optional[str] = None,
    limit: int = 10,
) -> List[ObservationRow]:
    """Return the most recent KnowledgeMemory observations matching the context.

    Used by KnowledgeMemoryService to fetch prior user interventions before
    an LLM call so they can be injected as Contextual Constraints.

    Filters are applied with AND logic when provided.  Ordered newest-first
    and capped at *limit* to avoid context-window bloat.

    Args:
        conn:      Open aiosqlite connection.
        dimension: If provided, restrict to observations for this dimension.
        phase:     If provided, restrict to observations from this phase.
        limit:     Maximum rows to return (default 10).

    Returns:
        List of ObservationRow ordered by timestamp DESC.
    """
    clauses: list[str] = []
    params: list[str] = []

    if dimension is not None:
        clauses.append("dimension = ?")
        params.append(dimension)
    if phase is not None:
        clauses.append("phase = ?")
        params.append(phase)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(str(limit))

    cursor = await conn.execute(
        f"""
        SELECT id, phase, node_id, dimension, base_value, amended_value, rationale, timestamp
        FROM knowledge_observations
        {where}
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        tuple(params),
    )
    rows = await cursor.fetchall()
    return [_row_to_observation(r) for r in rows]
