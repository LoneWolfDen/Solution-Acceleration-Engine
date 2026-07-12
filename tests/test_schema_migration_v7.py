"""tests/test_schema_migration_v7.py — Schema v7 migration coverage.

Covers Requirement A3.1/A3.4:
  - SCHEMA_VERSION == 7
  - review_job_artifact_snapshots table exists after init_database()
  - artifacts table has line_count/content_preview columns
  - re-running run_migrations() on an already-migrated connection is a no-op
    (idempotency)
"""

from __future__ import annotations

import asyncio

import aiosqlite
import pytest

from contexta.db.schema import SCHEMA_VERSION, run_migrations


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def _open_migrated_conn() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await run_migrations(conn)
    return conn


def test_schema_version_is_7():
    assert SCHEMA_VERSION == 7


def test_review_job_artifact_snapshots_table_exists(event_loop):
    async def _run():
        conn = await _open_migrated_conn()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='review_job_artifact_snapshots'"
        )
        row = await cursor.fetchone()
        await conn.close()
        return row

    row = event_loop.run_until_complete(_run())
    assert row is not None


def test_artifacts_table_has_new_columns(event_loop):
    async def _run():
        conn = await _open_migrated_conn()
        cursor = await conn.execute("PRAGMA table_info(artifacts)")
        rows = await cursor.fetchall()
        await conn.close()
        return {r["name"] for r in rows}

    columns = event_loop.run_until_complete(_run())
    assert "line_count" in columns
    assert "content_preview" in columns


def test_migration_is_idempotent_on_rerun(event_loop):
    async def _run():
        conn = await _open_migrated_conn()
        # Insert an artifact row so we can confirm the backfill UPDATE
        # re-running doesn't corrupt data.
        await conn.execute(
            "INSERT INTO projects (id, name, global_tags) VALUES (?, ?, ?)",
            ("p1", "P", "[]"),
        )
        await conn.execute(
            """
            INSERT INTO artifacts
                (id, project_id, title, content, source, source_url, filename,
                 tags, is_active, created_at, line_count, content_preview)
            VALUES ('a1', 'p1', 'T', 'line1\nline2\nline3', 'paste', NULL, NULL,
                    '[]', 1, 'now', 3, 'line1\nline2\nline3')
            """
        )
        await conn.commit()

        # Re-run migrations — should be a no-op, no errors, no data loss.
        await run_migrations(conn)

        cursor = await conn.execute(
            "SELECT version FROM schema_version LIMIT 1"
        )
        version_row = await cursor.fetchone()

        cursor = await conn.execute(
            "SELECT line_count, content_preview FROM artifacts WHERE id = 'a1'"
        )
        artifact_row = await cursor.fetchone()
        await conn.close()
        return version_row[0], artifact_row

    version, artifact_row = event_loop.run_until_complete(_run())
    assert version == SCHEMA_VERSION
    assert artifact_row["line_count"] == 3
    assert artifact_row["content_preview"] == "line1\nline2\nline3"


def test_backfill_computes_line_count_and_preview_for_existing_rows(event_loop):
    """Simulates a pre-migration artifact row (as if inserted under schema v6)
    and confirms the v6->v7 backfill computes correct values."""

    async def _run():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")

        # Manually create a v6-shaped artifacts table (no line_count/content_preview)
        # plus the schema_version marker, to simulate a pre-v7 database.
        await conn.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                global_tags TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE artifacts (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'paste', source_url TEXT,
                filename TEXT, tags TEXT NOT NULL DEFAULT '[]',
                is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            "CREATE TABLE schema_version (version INTEGER NOT NULL)"
        )
        await conn.execute("INSERT INTO schema_version (version) VALUES (6)")
        await conn.execute(
            "INSERT INTO projects (id, name, global_tags) VALUES ('p1', 'P', '[]')"
        )
        await conn.execute(
            """
            INSERT INTO artifacts
                (id, project_id, title, content, source, source_url, filename,
                 tags, is_active, created_at)
            VALUES ('a1', 'p1', 'T', 'alpha
beta
gamma', 'paste', NULL, NULL, '[]', 1, 'now')
            """
        )
        await conn.commit()

        await run_migrations(conn)

        cursor = await conn.execute(
            "SELECT line_count, content_preview FROM artifacts WHERE id = 'a1'"
        )
        row = await cursor.fetchone()
        await conn.close()
        return row

    row = event_loop.run_until_complete(_run())
    assert row["line_count"] == 3
    assert row["content_preview"] == "alpha\nbeta\ngamma"
