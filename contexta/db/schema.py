"""
contexta/db/schema.py — DDL statements, migration runner, and DB initialisation.

Design constraints enforced here:
  - nodes table includes version_tag (TEXT) and version_id (FK → versions) columns.
  - Foreign keys are enabled on every connection.
  - schema_version table tracks the applied migration level.
  - init_database() is the single entry point for all callers.

Data hierarchy (scope.md):
    Project (Root) → Version (Group) → Node/Artifact (Tagged) → Review → Proposal
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

# Bump this integer whenever new DDL is added to DDL_STATEMENTS.
# v1 → v2: Added ``versions`` table and ``version_id`` FK column on ``nodes``.
# v2 → v3: Added ``intelligence_layer`` table for Sprint 6 PromptOptimizer.
SCHEMA_VERSION = 3

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
    # Root container in the Project → Version → Artifact hierarchy.
    """
    CREATE TABLE IF NOT EXISTS projects (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        global_tags TEXT NOT NULL DEFAULT '[]'
    )
    """,

    # ── Versions ──────────────────────────────────────────────────────────────
    # Groups one or more Artifact nodes under a named iteration within a Project.
    # Enables cross-version comparison (scope.md — Comparison module).
    """
    CREATE TABLE IF NOT EXISTS versions (
        id          TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL REFERENCES projects(id),
        name        TEXT NOT NULL,
        description TEXT,
        created_at  TEXT NOT NULL
    )
    """,

    # ── Nodes ─────────────────────────────────────────────────────────────────
    # version_tag:  legacy human-assigned string label (backwards compat).
    # version_id:   FK → versions.id — the Version this node belongs to (nullable).
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
        version_tag      TEXT,
        version_id       TEXT REFERENCES versions(id)
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

    # ── Intelligence Layer ────────────────────────────────────────────────────
    # Stores learned insights produced by the Sprint 6 PromptOptimizer service.
    # Three insight types are written here:
    #   CITATION_TREND   — [ArtifactID:SectionID] citation frequency aggregates.
    #   CONFIDENCE_TREND — ConfidenceMatrix keyed by version_id (per-project).
    #   PROMPT_DELTA     — Recommended prompt adjustments from gate failures.
    #
    # project_id is nullable — NULL represents a global (cross-project) insight.
    # source_node_id is nullable — aggregated insights span multiple nodes.
    """
    CREATE TABLE IF NOT EXISTS intelligence_layer (
        id             TEXT PRIMARY KEY,
        project_id     TEXT REFERENCES projects(id),
        insight_type   TEXT NOT NULL,
        source_node_id TEXT REFERENCES nodes(id),
        payload_json   TEXT NOT NULL DEFAULT '{}',
        created_at     TEXT NOT NULL
    )
    """,
]


async def run_migrations(conn: "aiosqlite.Connection") -> None:
    """
    Apply all pending DDL statements and record the current schema version.

    Strategy:
      1. Run ALL DDL statements (CREATE TABLE IF NOT EXISTS — fully idempotent).
      2. Read the stored schema version.
      3. If stored version < SCHEMA_VERSION, apply any incremental column
         migrations and update the version record.

    Incremental migrations
    ----------------------
    v1 → v2:
      - ``versions`` table is created by step 1 (idempotent).
      - ``version_id TEXT REFERENCES versions(id)`` is added to ``nodes`` via
        ``ALTER TABLE``.  On a fresh install the column already exists from
        step 1, so the ALTER TABLE will silently fail — this is expected and
        safe.  On an existing v1 database the ALTER TABLE succeeds.
    """
    # Step 1: run ALL DDL (CREATE TABLE IF NOT EXISTS is idempotent)
    for statement in DDL_STATEMENTS:
        await conn.execute(statement)

    # Step 2: check stored schema version
    cursor = await conn.execute("SELECT version FROM schema_version LIMIT 1")
    row = await cursor.fetchone()
    stored_version: int = row[0] if row else 0

    if stored_version < SCHEMA_VERSION:
        # ── v0 / v1 → v2 ─────────────────────────────────────────────────────
        # Add version_id column to nodes for existing databases.
        # On a fresh install (v0) the DDL above already created the column;
        # the ALTER TABLE will raise OperationalError which we swallow silently.
        if stored_version < 2:
            try:
                await conn.execute(
                    "ALTER TABLE nodes ADD COLUMN version_id TEXT REFERENCES versions(id)"
                )
            except Exception:
                pass  # Column already exists on fresh installs — expected.

        # ── v2 → v3 ──────────────────────────────────────────────────────────
        # intelligence_layer is an entirely new table — no column alterations
        # are needed on existing tables.  The CREATE TABLE IF NOT EXISTS in
        # step 1 already handles both fresh installs and upgrades idempotently.
        # Nothing extra to do here.

        # ── Record new schema version ─────────────────────────────────────────
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
