"""tests/api/conftest.py — Shared fixtures for FastAPI integration tests."""

from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from contexta.db.schema import run_migrations


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_app(monkeypatch):
    """TestClient backed by an isolated file-based SQLite DB.

    A real file (not ``:memory:``) is required so that background pipeline
    tasks (``contexta/api/pipeline_bridge.py``), which open their *own*
    aiosqlite connection via ``load_api_config().db_path`` rather than
    reusing ``app.state.db``, see the same data written by the request
    handlers. ``CONTEXTA_DB_PATH`` is pointed at that file for the duration
    of the test so ``load_api_config()`` resolves to it.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)  # aiosqlite creates it fresh
    monkeypatch.setenv("CONTEXTA_DB_PATH", db_path)

    async def _open_db():
        conn = await aiosqlite.connect(db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await run_migrations(conn)
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

    from contexta.api.routers import admin, artifacts, projects, proposals, reviews, versions

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

    try:
        with TestClient(fresh_app, raise_server_exceptions=False) as client:
            yield client
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.fixture
def project_id():
    return "proj-1"


# ── Legacy fixture aliases ──────────────────────────────────────────────────
#
# tests/api/test_proposals.py predates the ``test_app`` fixture above (which
# builds the FastAPI app inline instead of via contexta.api.create_app) and
# still references the fixture names from that earlier conftest: ``client``,
# ``db_conn``, and ``review_id``. Rather than rewrite every test, alias them
# onto the current fixtures/helpers so both old and new tests share one DB
# setup path.


@pytest.fixture
def client(test_app):
    """Alias for ``test_app`` — kept for tests written against the earlier
    fixture name."""
    return test_app


@pytest.fixture
def db_conn(test_app):
    """Direct aiosqlite connection backing ``test_app`` (same DB instance)."""
    return test_app.app.state.db


@pytest.fixture
def version_id(test_app, project_id, event_loop):
    """A version under ``project_id`` with one linked artifact."""
    aid = test_app.post(
        "/api/artifacts",
        data={
            "project_id": project_id,
            "title": "Fixture Artifact",
            "source": "paste",
            "content": "content",
            "tags": "[]",
        },
    ).json()["artifact_id"]
    return test_app.post(
        "/api/versions",
        json={"project_id": project_id, "version_name": "v1", "artifact_ids": [aid]},
    ).json()["version_id"]


@pytest.fixture
def review_id(test_app, project_id, version_id, event_loop):
    """A review job under ``version_id``, forced to 'complete' status with a
    real exploration node attached — mirrors the terminal state the real
    pipeline leaves behind, which downstream proposal synthesis requires
    (it loads ``review_jobs.node_id`` and reads ``metadata_json['dimensions']``
    off the node to reconstruct ``ReviewNodePayload`` objects)."""
    from contexta.api import repositories as api_repo
    from contexta.db import repositories as db_repo
    from contexta.models.enums import ConfidenceEnum, ReviewDimensionEnum
    from contexta.models.payloads import ReviewNodePayload

    rid = test_app.post(
        "/api/reviews",
        json={"version_id": version_id, "persona_roles": ["Architect"], "context": ""},
    ).json()["review_id"]

    conn = test_app.app.state.db

    async def _complete_with_node():
        dim_dict = {
            "dimension": ReviewDimensionEnum.RISK.value,
            "overall_confidence": ConfidenceEnum.GREEN.value,
            "findings": [],
            "base_findings": [],
            "user_annotations": [],
            "raw_llm_response": "{}",
        }
        payload = ReviewNodePayload.model_validate(dim_dict)
        node = await db_repo.write_node(
            conn,
            project_id=project_id,
            parent_id=None,
            layer_type="exploration",
            node_name="Fixture Review Node",
            payload=payload,
            metadata={
                "persona": "Architect",
                "status": "complete",
                "dimensions": [dim_dict],
            },
            version_id=version_id,
        )
        await api_repo.update_review_job_status(
            conn, rid, status="complete", node_id=node.id
        )

    event_loop.run_until_complete(_complete_with_node())
    return rid
