"""
contexta/db/schema.py — DDL statements, migration runner, and DB initialisation.

Design constraints enforced here:
  - nodes table includes version_tag (TEXT) column.
  - Foreign keys are enabled on every connection.
  - schema_version table tracks the applied migration level.
  - init_database() is the single entry point for all callers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

# Bump this integer whenever new DDL is added to DDL_STATEMENTS.
SCHEMA_VERSION = 1

# All DDL statements executed in order during migration.
# CREATE TABLE IF NOT EXISTS ensures idempotency on re-runs.
DDL_STATEMENTS: list[str] = [
    # ── Schema version tracker ────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL
    )
    """,

    # ── Projects ──────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS projects (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        global_tags TEXT NOT NULL DEFAULT '[]'
    )
    """,

    # ── Nodes ─────────────────────────────────────────────────────────────────
    # version_tag: human-assigned label surfaced during fork / export workflows.
    """
    CREATE TABLE IF NOT EXISTS nodes (
        id               TEXT PRIMARY KEY,
        project_id       TEXT NOT NULL REFERENCES projects(id),
        parent_id        TEXT REFERENCES nodes(id),
        layer_type       TEXT NOT NULL,
        node_name        TEXT NOT NULL,
        metadata_json    TEXT NOT NULL DEFAULT '{}',
        content_markdown TEXT NOT NULL DEFAULT '',
        created_at       TEXT NOT NULL,
        version_tag      TEXT
    )
    """,

    # ── Prompt Blueprints ─────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS prompt_blueprints (
        id                 TEXT PRIMARY KEY,
        blueprint_name     TEXT NOT NULL,
        version_string     TEXT NOT NULL,
        master_prompt_text TEXT NOT NULL,
        is_active          INTEGER NOT NULL DEFAULT 0
    )
    """,

    # ── Global Client Insights ────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS global_client_insights (
        id                     TEXT PRIMARY KEY,
        client_or_industry_tag TEXT NOT NULL,
        observed_pattern       TEXT NOT NULL,
        frequency_count        INTEGER NOT NULL DEFAULT 1,
        last_updated           TEXT NOT NULL,
        UNIQUE(client_or_industry_tag, observed_pattern)
    )
    """,
]


async def run_migrations(conn: "aiosqlite.Connection") -> None:
    """
    Apply all pending DDL statements and record the current schema version.

    Strategy:
      1. Check whether schema_version table exists and read the stored version.
      2. If the stored version is already current, skip all DDL (idempotent).
      3. Otherwise execute every DDL statement in order, then write the version.

    This is a simple forward-only migration.  For this project scope a full
    Alembic-style runner is unnecessary overhead.
    """
    # Step 1: run ALL DDL (CREATE TABLE IF NOT EXISTS is idempotent)
    for statement in DDL_STATEMENTS:
        await conn.execute(statement)

    # Step 2: check stored schema version
    cursor = await conn.execute("SELECT version FROM schema_version LIMIT 1")
    row = await cursor.fetchone()
    stored_version: int = row[0] if row else 0

    if stored_version < SCHEMA_VERSION:
        if stored_version == 0:
            await conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
        else:
            await conn.execute(
                "UPDATE schema_version SET version = ?", (SCHEMA_VERSION,)
            )
        await conn.commit()
        logger.info("Database migrated to schema version %d.", SCHEMA_VERSION)
    else:
        await conn.commit()
        logger.debug("Database schema already at version %d.", stored_version)


async def init_database(db_path: str) -> "aiosqlite.Connection":
    """
    Open an aiosqlite connection, enable foreign-key enforcement, and run
    migrations.  Returns the open connection for use throughout the application.

    The caller is responsible for closing the connection on shutdown.

    Args:
        db_path: Filesystem path to the SQLite database file.  Will be created
                 if it does not exist.

    Returns:
        An open aiosqlite.Connection with migrations applied.
    """
    import aiosqlite  # local import keeps module importable without aiosqlite

    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await run_migrations(conn)
    return conn
