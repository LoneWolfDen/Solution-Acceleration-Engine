"""SQLite data-access layer — all raw SQL lives here.

Every function is ``async`` and accepts an ``aiosqlite.Connection`` as its
first argument.  No raw SQL appears outside this module.

Design contracts
----------------
- ``write_node()`` re-validates the payload against ``ReviewNodePayload`` before
  any ``INSERT``.  If validation fails the database is left unchanged.
- ``activate_blueprint()`` uses a single transaction to enforce the
  one-active-blueprint invariant atomically.
- ``upsert_insight()`` uses ``INSERT … ON CONFLICT … DO UPDATE`` to increment
  ``frequency_count`` without a separate SELECT.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite

from ..models.payloads import ReviewNodePayload
from .models import BlueprintRow, InsightRow, NodeRow, ProjectRow


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_project(row: aiosqlite.Row) -> ProjectRow:
    return ProjectRow(
        id=row["id"],
        name=row["name"],
        global_tags=json.loads(row["global_tags"]),
    )


def _row_to_node(row: aiosqlite.Row) -> NodeRow:
    return NodeRow(
        id=row["id"],
        project_id=row["project_id"],
        parent_id=row["parent_id"],
        layer_type=row["layer_type"],
        node_name=row["node_name"],
        metadata_json=row["metadata_json"],
        content_markdown=row["content_markdown"],
        created_at=row["created_at"],
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


# ── Projects ──────────────────────────────────────────────────────────────────


async def create_project(
    conn: aiosqlite.Connection,
    name: str,
    global_tags: List[str],
) -> ProjectRow:
    row_id = str(uuid.uuid4())
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
    async with conn.execute(
        "SELECT id, name, global_tags FROM projects WHERE id = ?", (project_id,)
    ) as cur:
        row = await cur.fetchone()
    return _row_to_project(row) if row else None


# ── Nodes ─────────────────────────────────────────────────────────────────────


async def write_node(
    conn: aiosqlite.Connection,
    project_id: str,
    parent_id: Optional[str],
    layer_type: str,
    node_name: str,
    payload: ReviewNodePayload,
    metadata: dict,
) -> NodeRow:
    """Validate *payload* then INSERT a new node row.

    Raises
    ------
    pydantic.ValidationError
        If the payload fails re-validation — no DB write occurs.
    """
    # Pydantic re-validation guard (Property 6)
    validated = ReviewNodePayload.model_validate(payload.model_dump())

    row_id = str(uuid.uuid4())
    now = _now_iso()
    metadata_str = json.dumps(metadata)
    content_md = validated.model_dump_json()

    await conn.execute(
        """
        INSERT INTO nodes
            (id, project_id, parent_id, layer_type, node_name,
             metadata_json, content_markdown, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (row_id, project_id, parent_id, layer_type, node_name,
         metadata_str, content_md, now),
    )
    await conn.commit()

    return NodeRow(
        id=row_id,
        project_id=project_id,
        parent_id=parent_id,
        layer_type=layer_type,
        node_name=node_name,
        metadata_json=metadata_str,
        content_markdown=content_md,
        created_at=now,
    )


async def get_node(
    conn: aiosqlite.Connection,
    node_id: str,
) -> Optional[NodeRow]:
    async with conn.execute(
        """SELECT id, project_id, parent_id, layer_type, node_name,
                  metadata_json, content_markdown, created_at
           FROM nodes WHERE id = ?""",
        (node_id,),
    ) as cur:
        row = await cur.fetchone()
    return _row_to_node(row) if row else None


async def list_nodes_for_project(
    conn: aiosqlite.Connection,
    project_id: str,
) -> List[NodeRow]:
    async with conn.execute(
        """SELECT id, project_id, parent_id, layer_type, node_name,
                  metadata_json, content_markdown, created_at
           FROM nodes WHERE project_id = ?
           ORDER BY created_at ASC""",
        (project_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_node(r) for r in rows]


async def list_all_nodes(conn: aiosqlite.Connection) -> List[NodeRow]:
    async with conn.execute(
        """SELECT id, project_id, parent_id, layer_type, node_name,
                  metadata_json, content_markdown, created_at
           FROM nodes ORDER BY created_at ASC"""
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_node(r) for r in rows]


async def fork_node(
    conn: aiosqlite.Connection,
    parent_node_id: str,
    new_node_name: str,
) -> NodeRow:
    """Create a new node branched from *parent_node_id*."""
    parent = await get_node(conn, parent_node_id)
    if parent is None:
        raise ValueError(f"Parent node {parent_node_id!r} not found")

    row_id = str(uuid.uuid4())
    now = _now_iso()
    await conn.execute(
        """
        INSERT INTO nodes
            (id, project_id, parent_id, layer_type, node_name,
             metadata_json, content_markdown, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (row_id, parent.project_id, parent_node_id,
         parent.layer_type, new_node_name,
         parent.metadata_json, parent.content_markdown, now),
    )
    await conn.commit()

    return NodeRow(
        id=row_id,
        project_id=parent.project_id,
        parent_id=parent_node_id,
        layer_type=parent.layer_type,
        node_name=new_node_name,
        metadata_json=parent.metadata_json,
        content_markdown=parent.content_markdown,
        created_at=now,
    )


# ── Prompt Blueprints ─────────────────────────────────────────────────────────


async def get_active_blueprint(
    conn: aiosqlite.Connection,
) -> Optional[BlueprintRow]:
    async with conn.execute(
        """SELECT id, blueprint_name, version_string, master_prompt_text, is_active
           FROM prompt_blueprints WHERE is_active = 1 LIMIT 1"""
    ) as cur:
        row = await cur.fetchone()
    return _row_to_blueprint(row) if row else None


async def activate_blueprint(
    conn: aiosqlite.Connection,
    blueprint_id: str,
) -> None:
    """Set is_active=1 for *blueprint_id*, is_active=0 for all others.

    Executed as a single transaction to preserve the one-active invariant.
    """
    await conn.execute("UPDATE prompt_blueprints SET is_active = 0")
    await conn.execute(
        "UPDATE prompt_blueprints SET is_active = 1 WHERE id = ?",
        (blueprint_id,),
    )
    await conn.commit()


async def save_blueprint_version(
    conn: aiosqlite.Connection,
    name: str,
    version: str,
    prompt_text: str,
) -> BlueprintRow:
    """Insert a new blueprint row — never modifies existing rows."""
    row_id = str(uuid.uuid4())
    await conn.execute(
        """INSERT INTO prompt_blueprints
               (id, blueprint_name, version_string, master_prompt_text, is_active)
           VALUES (?, ?, ?, ?, 0)""",
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
    async with conn.execute(
        """SELECT id, blueprint_name, version_string, master_prompt_text, is_active
           FROM prompt_blueprints ORDER BY blueprint_name, version_string"""
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_blueprint(r) for r in rows]


# ── Global Client Insights ────────────────────────────────────────────────────


async def upsert_insight(
    conn: aiosqlite.Connection,
    client_tag: str,
    pattern: str,
) -> InsightRow:
    """Increment frequency_count if (client_tag, pattern) exists; insert otherwise."""
    row_id = str(uuid.uuid4())
    now = _now_iso()
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

    async with conn.execute(
        """SELECT id, client_or_industry_tag, observed_pattern,
                  frequency_count, last_updated
           FROM global_client_insights
           WHERE client_or_industry_tag = ? AND observed_pattern = ?""",
        (client_tag, pattern),
    ) as cur:
        row = await cur.fetchone()

    return _row_to_insight(row)  # type: ignore[arg-type]


async def get_insights_for_tags(
    conn: aiosqlite.Connection,
    tags: List[str],
) -> List[InsightRow]:
    """Return all insight rows whose client_or_industry_tag is in *tags*."""
    if not tags:
        return []
    placeholders = ",".join("?" * len(tags))
    async with conn.execute(
        f"""SELECT id, client_or_industry_tag, observed_pattern,
                   frequency_count, last_updated
            FROM global_client_insights
            WHERE client_or_industry_tag IN ({placeholders})
            ORDER BY frequency_count DESC""",
        tags,
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_insight(r) for r in rows]
