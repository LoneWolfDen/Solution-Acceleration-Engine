"""
contexta/api/dependencies.py — FastAPI dependency injection providers.

get_db() yields the shared aiosqlite connection stored on app.state.
All route handlers receive this connection via Depends(get_db).

Reflex api_transformer compatibility
--------------------------------------
When the FastAPI app is mounted inside Reflex via ``api_transformer``, the
ASGI lifespan may not have completed before Reflex's compilation step
inspects the route graph.  Two failure modes exist:

  1. ``AttributeError: 'State' object has no attribute 'db'``
     Cause: lifespan hasn't fired yet; ``app.state.db`` is absent.

  2. ``TypeError: 'Connection' object is not an async generator``
     Cause: FastAPI ``Depends()`` expects an async generator (``yield``-based)
     so it can run cleanup after the response is sent.  Returning a bare
     connection object bypasses cleanup and leaks the connection.

Both are fixed here:
  - ``get_db`` is a proper ``async def … yield`` generator.
  - Primary path: reuse the lifespan-managed ``app.state.db`` connection.
  - Fallback path: open a fresh per-request connection when ``app.state.db``
    is absent (covers the startup-scan window and any unit-test context that
    doesn't run a full ASGI lifespan).  The fallback connection is closed in
    the generator's ``finally`` block so it is never leaked.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
from fastapi import Request

from .config import load_api_config

logger = logging.getLogger(__name__)

# Resolved once at import time so every fallback open targets the same file.
_DB_PATH: str = load_api_config().db_path


async def get_db(request: Request) -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Yield a shared aiosqlite connection for the duration of a single request.

    Primary path (normal operation)
    --------------------------------
    Reuses the connection opened by the ASGI lifespan and stored on
    ``app.state.db``.  The connection is *not* closed here — it is owned by
    the lifespan and shared across all requests.

    Fallback path (startup window / test context)
    ----------------------------------------------
    Opens a dedicated per-request connection when ``app.state.db`` is absent
    or ``None``.  The connection is always closed in the ``finally`` block,
    so it is never leaked regardless of whether the handler raises.
    """
    # ── Primary: lifespan-managed shared connection ───────────────────────────
    try:
        db: aiosqlite.Connection | None = getattr(request.app.state, "db", None)
    except AttributeError:
        # Starlette raises AttributeError on app.state access before the
        # application has been fully initialised (e.g. during Reflex's
        # internal route-graph compilation step).
        db = None

    if db is not None:
        yield db
        return

    # ── Fallback: per-request connection ─────────────────────────────────────
    logger.debug(
        "app.state.db not available — opening per-request fallback connection to %s",
        _DB_PATH,
    )
    # Ensure the parent directory exists (Docker / fresh checkout).
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    fallback: aiosqlite.Connection = await aiosqlite.connect(_DB_PATH)
    fallback.row_factory = aiosqlite.Row
    # Enable FK enforcement on every connection, consistent with init_database().
    await fallback.execute("PRAGMA foreign_keys = ON")
    try:
        yield fallback
    finally:
        await fallback.close()
