"""
contexta/api/dependencies.py — FastAPI dependency injection providers.

get_db() yields the single aiosqlite connection stored on app.state.
All route handlers receive this connection via Depends(get_db).
"""

from __future__ import annotations

import aiosqlite
from fastapi import Request


async def get_db(request: Request) -> aiosqlite.Connection:
    """
    Yield the shared aiosqlite connection from application state.

    The connection is opened once during application startup (lifespan) and
    closed on shutdown.  Route handlers must not close it themselves.
    """
    return request.app.state.db
