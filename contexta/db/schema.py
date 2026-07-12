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
import asyncio
import logging
import uuid
from pathlib import Path
import aiosqlite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

# Bump this integer whenever new DDL is added to DDL_STATEMENTS.
# v1 → v2: Added ``versions`` table and ``version_id`` FK column on ``nodes``.
# v2 → v3: Added ``intelligence_layer`` table for Sprint 6 PromptOptimizer.
# v3 → v4: Added web-API tables: artifacts, artifact_version_links,
#           review_jobs, proposal_jobs, app_config.
# v3 → v4: Added ``reviews`` and ``knowledge_observations`` tables for Knowledge Memory.
# v4 → v5: Added web-API tables: artifacts, artifact_version_links,
#           review_jobs, proposal_jobs, app_config.
# v5 → v6: Added ``review_links`` (M:N prior-review context junction) and
#           ``proposal_review_links`` (M:N proposal→review junction).
#           Data migration: existing proposal_jobs.review_job_id values are
#           copied into proposal_review_links before the column is retained for
#           backward compatibility.
# v6 → v7: Added ``line_count``/``content_preview`` columns to ``artifacts``
#           and the ``review_job_artifact_snapshots`` junction table (immutable
#           artifact provenance per review job).  Data migration: backfills
#           line_count/content_preview for existing artifact rows from their
#           stored ``content``.
SCHEMA_VERSION = 7

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

    # ── Artifacts (web API — v4) ──────────────────────────────────────────────
    # Ingested source documents.  Each artifact belongs to a project and can be
    # linked to one or more versions via artifact_version_links.
    # source: "upload" | "paste" | "url"
    # is_active: 1 = included in next analysis run, 0 = archived
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        id          TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL REFERENCES projects(id),
        title       TEXT NOT NULL,
        content     TEXT NOT NULL DEFAULT '',
        source      TEXT NOT NULL DEFAULT 'paste',
        source_url  TEXT,
        filename    TEXT,
        tags        TEXT NOT NULL DEFAULT '[]',
        is_active   INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT NOT NULL
    )
    """,

    # ── Artifact-Version Links (web API — v4) ─────────────────────────────────
    # Many-to-many junction: which artifacts are included in each version.
    """
    CREATE TABLE IF NOT EXISTS artifact_version_links (
        artifact_id TEXT NOT NULL REFERENCES artifacts(id),
        version_id  TEXT NOT NULL REFERENCES versions(id),
        PRIMARY KEY (artifact_id, version_id)
    )
    """,

    # ── Review Jobs (web API — v4) ────────────────────────────────────────────
    # Tracks async pipeline runs triggered via POST /api/reviews.
    # status: "queued" | "running" | "complete" | "failed"
    # node_id: set when the pipeline completes and writes a node row.
    """
    CREATE TABLE IF NOT EXISTS review_jobs (
        id               TEXT PRIMARY KEY,
        version_id       TEXT NOT NULL REFERENCES versions(id),
        persona_roles    TEXT NOT NULL DEFAULT '[]',
        context          TEXT NOT NULL DEFAULT '',
        status           TEXT NOT NULL DEFAULT 'queued',
        progress_message TEXT,
        node_id          TEXT REFERENCES nodes(id),
        created_at       TEXT NOT NULL,
        updated_at       TEXT NOT NULL
    )
    """,

    # ── Proposal Jobs (web API — v4) ──────────────────────────────────────────
    # Tracks async synthesis runs triggered via POST /api/proposals.
    """
    CREATE TABLE IF NOT EXISTS proposal_jobs (
        id               TEXT PRIMARY KEY,
        review_job_id    TEXT NOT NULL REFERENCES review_jobs(id),
        status           TEXT NOT NULL DEFAULT 'queued',
        progress_message TEXT,
        node_id          TEXT REFERENCES nodes(id),
        created_at       TEXT NOT NULL,
        updated_at       TEXT NOT NULL
    )
    """,

    # ── App Config (web API — v4) ─────────────────────────────────────────────
    # Key-value store for admin settings (API keys, thresholds, etc.).
    # API keys are stored as plain text server-side; never returned to the UI.
    """
    CREATE TABLE IF NOT EXISTS app_config (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT ''
    )
    """,
    # ── Reviews ───────────────────────────────────────────────────────────────
    # Stores a single arbitration run scoped to a Version.
    # ── Reviews ───────────────────────────────────────────────────────────────
    # Stores a single arbitration run scoped to a Version (Sprint 2).
    #
    # Columns:
    #   version_id            FK → versions.id (provenance anchor).
    #   persona_prompt        The LLM persona prompt used for this review run.
    #   user_context_text     Free-text user-supplied context or briefing.
    #   sme_augmentation_list JSON array of SME knowledge augmentation strings.
    #   dimension_output      JSON array of the 12-dimension review results.
    #   dimension_output      JSON array of the 12-dimension review results
    #                         (maps to spec field ``12_dimension_output`` — the
    #                         leading digit is not a valid SQL or Python
    #                         identifier start, so the column is named
    #                         ``dimension_output`` throughout).
    """
    CREATE TABLE IF NOT EXISTS reviews (
        id                    TEXT PRIMARY KEY,
        version_id            TEXT NOT NULL REFERENCES versions(id),
        persona_prompt        TEXT NOT NULL,
        user_context_text     TEXT NOT NULL,
        sme_augmentation_list TEXT NOT NULL DEFAULT '[]',
        dimension_output      TEXT NOT NULL DEFAULT '[]',
        created_at            TEXT NOT NULL
    )
    """,

    # ── Knowledge Observations ────────────────────────────────────────────────
    # Stores every user annotation (base → amended + rationale) so that the
    # KnowledgeMemoryService can retrieve prior interventions and inject them
    # as Contextual Constraints into subsequent LLM prompts.
    # No FK on node_id — observations may reference logical context keys that
    # span projects, enabling cross-project analytics.
    """
    CREATE TABLE IF NOT EXISTS knowledge_observations (
        id            TEXT PRIMARY KEY,
        phase         TEXT NOT NULL,
        node_id       TEXT NOT NULL,
        dimension     TEXT NOT NULL,
        base_value    TEXT NOT NULL,
        amended_value TEXT NOT NULL,
        rationale     TEXT NOT NULL,
        timestamp     TEXT NOT NULL
    )
    """,

    # ── Review Links (v6) ─────────────────────────────────────────────────────
    # M:N junction table — which prior completed reviews provide context for a
    # new review run (Gap 1: Prior Review Intelligence).
    #
    # Composite PK on (review_job_id, linked_review_id) prevents duplicate links.
    # CHECK constraint prevents self-links.
    # Both FK columns reference review_jobs.id.
    """
    CREATE TABLE IF NOT EXISTS review_links (
        review_job_id    TEXT NOT NULL REFERENCES review_jobs(id),
        linked_review_id TEXT NOT NULL REFERENCES review_jobs(id),
        PRIMARY KEY (review_job_id, linked_review_id),
        CHECK(review_job_id != linked_review_id)
    )
    """,

    # ── Proposal Review Links (v6) ────────────────────────────────────────────
    # M:N junction table — which completed review jobs feed a given proposal
    # synthesis run (Gap 2: Multi-Review Proposal Re-Architecture).
    #
    # Composite PK on (proposal_job_id, review_job_id).
    # proposal_jobs.review_job_id is RETAINED for backward compatibility with
    # any existing code that reads the single-FK column; this junction table is
    # the canonical source of truth for multi-review proposals.
    """
    CREATE TABLE IF NOT EXISTS proposal_review_links (
        proposal_job_id TEXT NOT NULL REFERENCES proposal_jobs(id),
        review_job_id   TEXT NOT NULL REFERENCES review_jobs(id),
        PRIMARY KEY (proposal_job_id, review_job_id)
    )
    """,

    # ── Review Job Artifact Snapshots (v7) ────────────────────────────────────
    # Immutable record of exactly which artifacts were active on a version at
    # the moment a review job was created (Requirement A2).  Distinct from the
    # mutable "current" artifact set exposed via artifact_version_links — later
    # changes to artifact.is_active must NOT retroactively alter this snapshot.
    """
    CREATE TABLE IF NOT EXISTS review_job_artifact_snapshots (
        review_job_id TEXT NOT NULL REFERENCES review_jobs(id),
        artifact_id   TEXT NOT NULL REFERENCES artifacts(id),
        PRIMARY KEY (review_job_id, artifact_id)
    )
    """,
]


async def run_migrations(conn: "aiosqlite.Connection") -> None:
    
    #Apply all pending DDL statements and record the current schema version.

    #Strategy:
    #  1. Run ALL DDL statements (CREATE TABLE IF NOT EXISTS — fully idempotent).
    #  2. Read the stored schema version.
    #  3. If stored version < SCHEMA_VERSION, apply any incremental column
    #     migrations and update the version record.

    #Incremental migrations
    #----------------------
    #v1 → v2:
    #  - ``versions`` table is created by step 1 (idempotent).
    #  - ``version_id TEXT REFERENCES versions(id)`` is added to ``nodes`` via
    #    ``ALTER TABLE``.  On a fresh install the column already exists from
    #    step 1, so the ALTER TABLE will silently fail — this is expected and
    #    safe.  On an existing v1 database the ALTER TABLE succeeds.
    
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

        # ── v3 → v4 ──────────────────────────────────────────────────────────
        # Five new tables (artifacts, artifact_version_links, review_jobs,
        # proposal_jobs, app_config).  All created by CREATE TABLE IF NOT
        # EXISTS in step 1 — no column alterations required on existing tables.
        # reviews and knowledge_observations are entirely new tables — no
        # column alterations needed.  Handled idempotently by step 1 above.
        # Nothing extra to do here.

        # ── v3 → v4 ──────────────────────────────────────────────────────────
        # reviews and knowledge_observations are entirely new tables.
        # Handled idempotently by step 1. Nothing extra to do here.

        # ── v4 → v5 ──────────────────────────────────────────────────────────
        # Web-API tables (artifacts, artifact_version_links, review_jobs,
        # proposal_jobs, app_config) are entirely new tables.
        # Handled idempotently by step 1. Nothing extra to do here.

        # ── v5 → v6 ──────────────────────────────────────────────────────────
        # Two new M:N junction tables (review_links, proposal_review_links)
        # are created idempotently by step 1 above.
        #
        # Data migration: copy any existing 1:1 proposal→review links that are
        # stored in proposal_jobs.review_job_id into the new junction table so
        # that all downstream queries can rely solely on proposal_review_links.
        # INSERT OR IGNORE is safe to re-run; duplicate inserts are silently
        # skipped, preserving idempotency on repeated startups.
        if stored_version < 6:
            await conn.execute(
                """
                INSERT OR IGNORE INTO proposal_review_links (proposal_job_id, review_job_id)
                SELECT id, review_job_id
                FROM proposal_jobs
                WHERE review_job_id IS NOT NULL
                """
            )
            logger.info(
                "v5→v6 data migration: proposal_jobs.review_job_id values "
                "copied into proposal_review_links."
            )

        # ── v6 → v7 ──────────────────────────────────────────────────────────
        # Add line_count/content_preview columns to artifacts (existing table)
        # and backfill them from stored content.  review_job_artifact_snapshots
        # is an entirely new table, handled idempotently by step 1 above.
        if stored_version < 7:
            try:
                await conn.execute(
                    "ALTER TABLE artifacts ADD COLUMN line_count INTEGER NOT NULL DEFAULT 0"
                )
            except Exception:
                pass  # Column already exists on fresh installs — expected.
            try:
                await conn.execute(
                    "ALTER TABLE artifacts ADD COLUMN content_preview TEXT NOT NULL DEFAULT ''"
                )
            except Exception:
                pass  # Column already exists on fresh installs — expected.

            # Backfill: line_count = number of newline-delimited lines in
            # content (LENGTH(content) - LENGTH(REPLACE(content, char(10), ''))
            # counts newline characters; +1 accounts for the last line without
            # a trailing newline). content_preview = first 280 characters.
            # Idempotent — safe to re-run on every startup.
            await conn.execute(
                """
                UPDATE artifacts
                SET line_count = LENGTH(content) - LENGTH(REPLACE(content, char(10), '')) + 1,
                    content_preview = SUBSTR(content, 1, 280)
                """
            )
            logger.info(
                "v6→v7 data migration: artifacts.line_count/content_preview "
                "backfilled from stored content."
            )

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


async def seed_data(conn: "aiosqlite.Connection") -> None:
    """
    Insert a Demo Project if the projects table is empty.

    Called by init_database() after migrations so that a fresh install always
    has at least one project for the UI to display.  Skipped when the table
    already contains rows (i.e. on every subsequent startup).
    """
    cursor = await conn.execute("SELECT COUNT(*) FROM projects")
    row = await cursor.fetchone()
    count: int = row[0] if row else 0

    if count == 0:
        project_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO projects (id, name, global_tags) VALUES (?, ?, ?)",
            (project_id, "Demo Project", '["demo"]'),
        )
        await conn.commit()
        logger.info("Seeded Demo Project (id=%s).", project_id)
    else:
        logger.debug("projects table non-empty (%d rows) — skipping seed.", count)


async def init_database(db_path: str) -> "aiosqlite.Connection":
    """
    Open an aiosqlite connection, enable foreign-key enforcement, run
    migrations, and seed initial data if the database is empty.

    The caller is responsible for closing the connection on shutdown.

    Args:
        db_path: Filesystem path to the SQLite database file.  Will be created
                 if it does not exist.

    Returns:
        An open aiosqlite.Connection with migrations and seed data applied.
    """
    import aiosqlite  # local import keeps module importable without aiosqlite

    # Ensure the parent directory exists (e.g. ./data/ on local dev).
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await run_migrations(conn)
    await seed_data(conn)
    return conn
