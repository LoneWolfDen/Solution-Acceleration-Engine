"""
tests/api/conftest.py — Shared fixtures for API integration tests.

Fixtures
--------
app         — FastAPI instance wired to a fresh in-memory SQLite DB per test.
client      — Synchronous TestClient wrapping the app (httpx transport).
db_conn     — Direct aiosqlite connection to the same in-memory DB (for setup helpers).
project_id  — A pre-inserted project row, available to every test that needs one.

Design
------
- Each test gets its own isolated `:memory:` DB via create_app(":memory:").
- The TestClient uses ``with`` context manager to trigger lifespan (startup/shutdown).
- No LLM calls are made anywhere; pipeline background tasks are stubs.
- The ``CONTEXTA_LLM_BACKEND`` env-var is NOT required by the API layer itself,
  only by ContextaConfig (used by the TUI).  The API's create_app() catches
  ConfigError and falls back to a default path, so tests pass without it.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from contexta.api import create_app
from contexta.api.config_store import AdminConfigStore


# ── App / Client ──────────────────────────────────────────────────────────────


@pytest.fixture()
def app():
    """FastAPI app backed by a fresh in-memory SQLite DB."""
    return create_app(db_path=":memory:")


@pytest.fixture()
def client(app) -> Generator[TestClient, None, None]:
    """Synchronous TestClient that triggers lifespan startup/shutdown."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── Direct DB access (for test setup helpers) ─────────────────────────────────


@pytest.fixture()
def db_conn(app, client):
    """
    Return the live aiosqlite connection from app.state.db.

    ``client`` fixture is listed as a dependency to ensure the lifespan has
    already run (i.e. the DB is open and migrations applied).
    """
    return app.state.db


# ── Pre-seeded data helpers ───────────────────────────────────────────────────


def _run(coro):
    """Run a coroutine in the current event loop (test process loop)."""
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture()
def project_id(db_conn) -> str:
    """Insert a project and return its ID."""
    from contexta.db import repositories as repo
    row = _run(repo.create_project(db_conn, "Test Project", ["test"]))
    return row.id


@pytest.fixture()
def version_id(db_conn, project_id) -> str:
    """Insert a version under project_id and return its ID."""
    from contexta.db import repositories as repo
    row = _run(repo.create_version(db_conn, project_id, "v1.0"))
    return row.id


@pytest.fixture()
def artifact_id(db_conn, project_id) -> str:
    """Insert an exploration node (artifact) and return its ID."""
    import json
    from datetime import datetime, timezone
    node_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    meta = {"tags": ["test-tag"], "is_active": True, "source": "paste"}
    _run(db_conn.execute(
        """
        INSERT INTO nodes
            (id, project_id, parent_id, layer_type, node_name,
             metadata_json, content_markdown, created_at, version_tag, version_id)
        VALUES (?, ?, NULL, 'exploration', ?, ?, ?, ?, NULL, NULL)
        """,
        (node_id, project_id, "Test Artifact", json.dumps(meta), "content", now),
    ))
    _run(db_conn.commit())
    return node_id


@pytest.fixture()
def review_id(db_conn, project_id, version_id) -> str:
    """Insert a synthesis node (review) under version_id and return its ID."""
    import json
    from datetime import datetime, timezone
    node_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    meta = {"persona": "risk-analyst", "status": "complete"}
    _run(db_conn.execute(
        """
        INSERT INTO nodes
            (id, project_id, parent_id, layer_type, node_name,
             metadata_json, content_markdown, created_at, version_tag, version_id)
        VALUES (?, ?, NULL, 'synthesis', ?, ?, '', ?, NULL, ?)
        """,
        (node_id, project_id, "Review — test", json.dumps(meta), now, version_id),
    ))
    _run(db_conn.commit())
    return node_id
