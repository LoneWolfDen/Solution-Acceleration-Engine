"""
contexta/api/dependencies.py — FastAPI dependency injection providers.

get_db() yields the single aiosqlite connection stored on app.state.
All route handlers receive this connection via Depends(get_db).
"""

from __future__ import annotations

import os
import aiosqlite
from fastapi import Request

# Define where your local database file lives
DB_PATH = "contexta.db"

async def get_db(request: Request) -> aiosqlite.Connection:
    """
    Yield the shared aiosqlite connection from application state.
    Fallback to opening a local connection dynamically if the state is uninitialized.
    """
    # 1. Try to fetch the pre-existing connection from Reflex/FastAPI app state
    try:
        if hasattr(request.app.state, "db") and request.app.state.db is not None:
            return request.app.state.db
    except AttributeError:
        pass

    # 2. Fallback: If it's missing, open an asynchronous connection on the fly
    # Ensure the DB file exists before opening it
    if not os.path.exists(DB_PATH):
        # Trigger an empty file creation if it doesn't exist yet
        open(DB_PATH, "a").close()

    conn = await aiosqlite.connect(DB_PATH)
    # Enable row factory so results act like dictionaries (standard for this setup)
    conn.row_factory = aiosqlite.Row
    return conn
