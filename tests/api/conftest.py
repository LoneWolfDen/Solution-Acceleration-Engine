"""
tests/api/conftest.py — Shared fixtures for FastAPI integration tests.

Uses an in-memory SQLite database per test session so tests are isolated
from each other and from any on-disk development database.
No LLM calls are made during these tests.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from contexta.api import app as _base_app
from contexta.db.schema import run_migrations


# ── In-memory DB fixture ──────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Single asyncio event loop for the session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_app():
    """
    Return a FastAPI TestClient backed by an in-memory SQLite DB.

    The DB is seeded with a single Demo Project so tests that need an
    existing project can reference it without setup boilerplate.
    """
    async def _open_db():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await run_migrations(conn)
        # Insert a known project for tests that need one
        await conn.execute(
            "INSERT INTO projects (id, name, global_tags) VALUES (?, ?, ?)",
            ("proj-1", "Test Project", '["test"]'),
        )
        await conn.commit()
        return conn

    @asynccontextmanager
    async def _lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        application.state.db = await _open_db()
        yield
        await application.state.db.close()

    # Build a fresh app instance with the in-memory lifespan
    from contexta.api.routers import admin, artifacts, projects, proposals, reviews, versions
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    fresh_app = FastAPI(lifespan=_lifespan)
    fresh_app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @fresh_app.exception_handler(StarletteHTTPException)
    async def _http_exc(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    @fresh_app.exception_handler(Exception)
    async def _unhandled_exc(request, exc):
        return JSONResponse(status_code=500, content={"error": str(exc)})

    fresh_app.get("/api/health")(lambda: {"status": "ok", "error": None})
    fresh_app.include_router(projects.router, prefix="/api")
    fresh_app.include_router(versions.router, prefix="/api")
    fresh_app.include_router(artifacts.router, prefix="/api")
    fresh_app.include_router(reviews.router, prefix="/api")
    fresh_app.include_router(proposals.router, prefix="/api")
    fresh_app.include_router(admin.router, prefix="/api")

    with TestClient(fresh_app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def project_id():
    return "proj-1"
