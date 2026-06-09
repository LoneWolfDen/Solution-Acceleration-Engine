"""SQLite DDL definitions and migration runner.

``init_database()`` is the public entry point called at application startup.
It opens an ``aiosqlite`` connection, enables foreign-key enforcement, and
delegates to ``run_migrations()`` to apply outstanding DDL.

All five tables are created with ``IF NOT EXISTS`` guards so the function is
safe to call on every startup against an already-initialised database.
"""

from __future__ import annotations

import aiosqlite

# ── Constants ─────────────────────────────────────────────────────────────────

SCHEMA_VERSION = 1

# DDL executed in order on every fresh database.
_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        global_tags TEXT NOT NULL DEFAULT '[]'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nodes (
        id               TEXT PRIMARY KEY,
        project_id       TEXT NOT NULL REFERENCES projects(id),
        parent_id        TEXT REFERENCES nodes(id),
        layer_type       TEXT NOT NULL,
        node_name        TEXT NOT NULL,
        metadata_json    TEXT NOT NULL DEFAULT '{}',
        content_markdown TEXT NOT NULL DEFAULT '',
        created_at       TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prompt_blueprints (
        id                 TEXT PRIMARY KEY,
        blueprint_name     TEXT NOT NULL,
        version_string     TEXT NOT NULL,
        master_prompt_text TEXT NOT NULL,
        is_active          INTEGER NOT NULL DEFAULT 0
    )
    """,
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


# ── Migration runner ──────────────────────────────────────────────────────────


async def run_migrations(conn: aiosqlite.Connection) -> None:
    """Apply outstanding DDL migrations to *conn*.

    Checks the ``schema_version`` table; if the version is below
    ``SCHEMA_VERSION`` (or the table is empty), runs all DDL statements and
    records the current version.
    """
    # Ensure schema_version table exists first
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    await conn.commit()

    async with conn.execute("SELECT version FROM schema_version LIMIT 1") as cur:
        row = await cur.fetchone()

    current_version = row[0] if row else 0

    if current_version < SCHEMA_VERSION:
        for ddl in _DDL_STATEMENTS:
            await conn.execute(ddl)

        if row is None:
            await conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
        else:
            await conn.execute(
                "UPDATE schema_version SET version = ?", (SCHEMA_VERSION,)
            )

        await conn.commit()


# ── Connection factory ────────────────────────────────────────────────────────


async def init_database(db_path: str) -> aiosqlite.Connection:
    """Open the SQLite database at *db_path*, enable foreign keys, and migrate.

    Parameters
    ----------
    db_path:
        Filesystem path to the SQLite file.  The file is created if it does
        not exist (SQLite default behaviour).

    Returns
    -------
    aiosqlite.Connection
        An open, migrated connection ready for use.
    """
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await run_migrations(conn)
    return conn
