#!/usr/bin/env python3
"""
scripts/init_db.py — Standalone database initialisation script.

Usage
-----
    # Standard local dev (creates/migrates contexta.db in the project root):
    python scripts/init_db.py

    # Custom path (e.g. Docker volume mount):
    CONTEXTA_DB_PATH=/app/data/contexta.db python scripts/init_db.py

What it does
------------
1. Resolves the DB path from CONTEXTA_DB_PATH env var (falls back to the
   same default used by WebAPIConfig: <project_root>/contexta.db).
2. Creates the parent directory if it doesn't exist.
3. Calls init_database() which runs all DDL statements
   (CREATE TABLE IF NOT EXISTS — fully idempotent) and applies any pending
   incremental migrations via run_migrations().
4. Seeds a Demo Project if the projects table is empty (first run only).
5. Prints the table list so the operator can confirm schema was applied.

Safe to re-run: all DDL is idempotent; seed data is skipped after first run.

Replaces the inline python -c "..." blocks that were scattered across
LOCAL_SETUP_GUIDE.md, entrypoint.sh, and CI scripts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import sys
from pathlib import Path

# Make sure the project root is on sys.path so contexta.* imports work when
# this script is run directly (not via `python -m`).
_PROJECT_ROOT = Path(__file__).parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contexta.db.schema import init_database  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)


def _resolve_db_path() -> str:
    """Return the canonical DB path, honouring CONTEXTA_DB_PATH if set."""
    env_path = os.environ.get("CONTEXTA_DB_PATH", "").strip()
    if env_path:
        return env_path
    # Mirror the default in WebAPIConfig so there is a single source of truth.
    return str(_PROJECT_ROOT / "contexta.db")


async def main() -> None:
    db_path = _resolve_db_path()
    logger.info("Target database: %s", db_path)

    # Ensure parent directory exists (required for Docker volume mounts and
    # fresh checkouts where ./data doesn't exist yet).
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = await init_database(db_path)
    await conn.close()
    logger.info("Database initialised successfully.")

    # Print the applied tables for visual confirmation.
    sync_conn = sqlite3.connect(db_path)
    tables = [
        row[0]
        for row in sync_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    sync_conn.close()

    logger.info("Tables present (%d): %s", len(tables), ", ".join(tables))

    expected = {
        "app_config",
        "artifact_version_links",
        "artifacts",
        "global_client_insights",
        "intelligence_layer",
        "knowledge_observations",
        "nodes",
        "projects",
        "prompt_blueprints",
        "proposal_jobs",
        "review_jobs",
        "reviews",
        "schema_version",
        "versions",
    }
    missing = expected - set(tables)
    if missing:
        logger.warning("Missing expected tables: %s", ", ".join(sorted(missing)))
        sys.exit(1)
    else:
        logger.info("All expected tables are present. Database is ready.")


if __name__ == "__main__":
    asyncio.run(main())
