"""contexta/api/dependencies.py — FastAPI dependency injection.

Provides:
    get_db()     — yields an aiosqlite connection initialised with schema v4.
    get_config() — returns the active LLM/threshold config from the DB.

The DB path is read from the CONTEXTA_DB_PATH environment variable
(default: ``/data/contexta.db``).  Tests override this to ``:memory:`` by
setting CONTEXTA_DB_PATH before importing the module or by using the
``override_db`` fixture.
"""

from __future__ import annotations

import os
from typing import AsyncIterator

import aiosqlite

from ..db.schema import init_database

# ── DB path ───────────────────────────────────────────────────────────────────

_DEFAULT_DB_PATH = os.environ.get("CONTEXTA_DB_PATH", "/data/contexta.db")


async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Yield a fully-migrated aiosqlite connection.

    A new connection is opened for each request and closed on teardown.
    Foreign keys are enabled and all schema migrations are applied by
    ``init_database()``.
    """
    db_path = os.environ.get("CONTEXTA_DB_PATH", _DEFAULT_DB_PATH)
    conn = await init_database(db_path)
    try:
        yield conn
    finally:
        await conn.close()
