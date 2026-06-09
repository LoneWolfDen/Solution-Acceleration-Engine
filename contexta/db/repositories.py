"""SQLite repository functions — async read/write operations.

All functions accept an ``aiosqlite.Connection`` as their first argument.
This module is the **only** place in the codebase that contains raw SQL.

Sprint 3 note
-------------
Full implementations are scheduled for Task 3 (Sprint DB layer).  This
module currently exposes the minimal stubs required for the pipeline layer
(``dimension_runner``, ``advisor``) to import and for their test doubles to
patch against.

Each stub raises ``NotImplementedError`` at call-time so any accidental
live invocation fails loudly rather than silently returning bad data.
"""

from __future__ import annotations

from typing import List, Optional

from .models import BlueprintRow, InsightRow, NodeRow, ProjectRow


# ── Projects ──────────────────────────────────────────────────────────────────


async def create_project(
    conn,
    name: str,
    global_tags: List[str],
) -> ProjectRow:
    raise NotImplementedError("create_project not yet implemented")


async def get_project(
    conn,
    project_id: str,
) -> Optional[ProjectRow]:
    raise NotImplementedError("get_project not yet implemented")


# ── Nodes ─────────────────────────────────────────────────────────────────────


async def write_node(
    conn,
    project_id: str,
    parent_id: Optional[str],
    layer_type: str,
    node_name: str,
    payload,
    metadata: dict,
) -> NodeRow:
    """Validate payload and write a single node row atomically.

    Raises ``NotImplementedError`` until the DB layer sprint is complete.
    Tests patch this function at ``contexta.db.repositories.write_node``.
    """
    raise NotImplementedError("write_node not yet implemented")


async def get_node(
    conn,
    node_id: str,
) -> Optional[NodeRow]:
    raise NotImplementedError("get_node not yet implemented")


async def list_nodes_for_project(
    conn,
    project_id: str,
) -> List[NodeRow]:
    raise NotImplementedError("list_nodes_for_project not yet implemented")


async def fork_node(
    conn,
    parent_node_id: str,
    new_node_name: str,
) -> NodeRow:
    raise NotImplementedError("fork_node not yet implemented")


async def list_all_nodes(conn) -> List[NodeRow]:
    raise NotImplementedError("list_all_nodes not yet implemented")


# ── Prompt blueprints ─────────────────────────────────────────────────────────


async def get_active_blueprint(conn) -> Optional[BlueprintRow]:
    raise NotImplementedError("get_active_blueprint not yet implemented")


async def activate_blueprint(conn, blueprint_id: str) -> None:
    raise NotImplementedError("activate_blueprint not yet implemented")


async def save_blueprint_version(
    conn,
    name: str,
    version: str,
    prompt_text: str,
) -> BlueprintRow:
    raise NotImplementedError("save_blueprint_version not yet implemented")


async def list_blueprints(conn) -> List[BlueprintRow]:
    raise NotImplementedError("list_blueprints not yet implemented")


# ── Global client insights ────────────────────────────────────────────────────


async def upsert_insight(
    conn,
    client_tag: str,
    pattern: str,
) -> InsightRow:
    raise NotImplementedError("upsert_insight not yet implemented")


async def get_insights_for_tags(
    conn,
    tags: List[str],
) -> List[InsightRow]:
    """Return all ``InsightRow`` objects whose tag appears in ``tags``.

    Raises ``NotImplementedError`` until the DB layer sprint is complete.
    Tests patch this function at
    ``contexta.db.repositories.get_insights_for_tags``.
    """
    raise NotImplementedError("get_insights_for_tags not yet implemented")
