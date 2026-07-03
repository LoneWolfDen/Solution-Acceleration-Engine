"""Shared fixtures for Milestone 5 API integration tests.

Design:
  - Every test gets a fully-isolated in-memory SQLite database.
  - The FastAPI dependency ``get_db`` is overridden to yield that DB.
  - Background pipeline tasks (reviews, proposals) are replaced by a no-op
    stub so no LLM calls are made and no extra DB connections are opened.
  - All tests run via the synchronous ``TestClient`` (HTTPX-based) which
    is fully compatible with async FastAPI routes.

No LLM calls are made during any test in this module.
"""

from __future__ import annotations

import os
import pytest
import pytest_asyncio

# Point the dependency at :memory: BEFORE the app module is imported.
os.environ.setdefault("CONTEXTA_DB_PATH", ":memory:")


from contexta.api import app
from contexta.api.dependencies import get_db
from contexta.db.schema import init_database

from httpx import AsyncClient, ASGITransport
import aiosqlite


# ── In-memory DB fixture ──────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def mem_db() -> aiosqlite.Connection:
    """Yield a fresh in-memory SQLite DB with all migrations applied."""
    conn = await init_database(":memory:")
    try:
        yield conn
    finally:
        await conn.close()


# ── TestClient fixture ────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(mem_db: aiosqlite.Connection):
    """Yield an HTTPX AsyncClient with get_db overridden to use mem_db.

    The background pipeline tasks are also stubbed out so tests never
    trigger real LLM calls or open secondary DB connections.
    """
    from contexta.api.routers import reviews as reviews_mod
    from contexta.api.routers import proposals as proposals_mod

    # Stub pipeline background tasks — do nothing, no LLM, no extra DB.
    async def _noop_pipeline(review_id: str, db_path: str) -> None:
        pass

    async def _noop_proposal(proposal_id: str, db_path: str) -> None:
        pass

    original_pipeline = reviews_mod._run_pipeline_stub
    original_proposal = proposals_mod._run_proposal_stub
    reviews_mod._run_pipeline_stub = _noop_pipeline
    proposals_mod._run_proposal_stub = _noop_proposal

    async def _override_db():
        yield mem_db

    app.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    reviews_mod._run_pipeline_stub = original_pipeline
    proposals_mod._run_proposal_stub = original_proposal


# ── Seed helpers (used across multiple test modules) ─────────────────────────

async def seed_project(db: aiosqlite.Connection, name: str = "Test Project") -> str:
    """Insert a project row and return its id."""
    from contexta.db.repositories import create_project
    row = await create_project(db, name, [])
    return row.id


async def seed_artifact(
    db: aiosqlite.Connection,
    project_id: str,
    title: str = "Test Artifact",
    is_active: bool = True,
) -> str:
    """Insert an artifact row and return its id."""
    import uuid
    from datetime import datetime, timezone
    import json

    aid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO artifacts (id, project_id, title, source, content, tags, is_active, created_at) "
        "VALUES (?, ?, ?, 'paste', 'test content', '[]', ?, ?)",
        (aid, project_id, title, 1 if is_active else 0, now),
    )
    await db.commit()
    return aid


async def seed_version(
    db: aiosqlite.Connection,
    project_id: str,
    artifact_ids: list[str],
    name: str = "v1",
) -> str:
    """Insert a version row with pinned artifacts and return its id."""
    from contexta.db.repositories import create_version

    vrow = await create_version(db, project_id, name)
    for aid in artifact_ids:
        await db.execute(
            "INSERT INTO version_artifacts (version_id, artifact_id) VALUES (?, ?)",
            (vrow.id, aid),
        )
    await db.commit()
    return vrow.id


async def seed_review(
    db: aiosqlite.Connection,
    version_id: str,
    status: str = "complete",
) -> str:
    """Insert a review row and return its id."""
    import uuid
    from datetime import datetime, timezone

    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO reviews (id, version_id, persona_roles, context, status, run_date) "
        "VALUES (?, ?, '[]', '', ?, ?)",
        (rid, version_id, status, now),
    )
    await db.commit()
    return rid
