"""
contexta/api/dependencies.py — FastAPI dependency injection helpers.

get_db()     — yields an aiosqlite connection from app state.
get_config() — returns the AdminConfigStore singleton from app state.
"""

from __future__ import annotations

from typing import AsyncGenerator

import aiosqlite
from fastapi import Depends, Request


async def get_db(request: Request) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yield the shared aiosqlite connection stored in app.state.db."""
    yield request.app.state.db


async def get_config(request: Request) -> "AdminConfigStore":  # type: ignore[name-defined]
    """Return the AdminConfigStore singleton from app state."""
    return request.app.state.config_store
