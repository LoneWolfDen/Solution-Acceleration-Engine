"""
contexta/api/__init__.py — FastAPI application and route handlers.

Provides a REST API over the Contexta data layer for the Reflex web frontend.
All database access delegates to contexta.db.repositories; this module stays
thin (validation, mapping, HTTP semantics only).

The app is intentionally decoupled from ContextaConfig: it only needs the DB
path, which it reads directly from the CONTEXTA_DB_PATH environment variable
(falling back to the same project-relative default used by config.py).  This
means the API server can start without CONTEXTA_LLM_BACKEND being set — the
LLM backend is only required when running the pipeline via the TUI.

Run with:
    uvicorn contexta.api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import aiosqlite
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# ── CORS origin resolution ────────────────────────────────────────────────────
# In a Codespace the browser origin is https://{CODESPACE_NAME}-3000.app.github.dev.
# When allow_origins=["*"] with allow_credentials=True the CORS spec requires the
# server to echo the concrete request Origin — Starlette does this automatically.
# However, specifying origins explicitly is more correct and avoids edge cases with
# some browser pre-flight implementations.
_CODESPACE_NAME: str = os.environ.get("CODESPACE_NAME", "")

from ..db import repositories as repo
from ..db.schema import init_database
from .schemas import (
    NodeDetailResponse,
    NodeSummaryResponse,
    ProjectDetailResponse,
    ProjectResponse,
    VersionResponse,
)

# ── DB path resolution ────────────────────────────────────────────────────────
# Mirrors the logic in config.py so that both entry points resolve to the same
# default without requiring ContextaConfig (which demands LLM_BACKEND).
_PROJECT_ROOT: Path = Path(__file__).parents[2]
_DEFAULT_DB_PATH: str = str(_PROJECT_ROOT / "data" / "contexta.db")
_DB_PATH: str = os.environ.get("CONTEXTA_DB_PATH", _DEFAULT_DB_PATH)


# ── Lifespan: one shared connection for the lifetime of the process ───────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Open the DB on startup; close it cleanly on shutdown."""
    app.state.db = await init_database(_DB_PATH)
    yield
    await app.state.db.close()


# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Contexta API",
    version="0.1.0",
    description="REST API for the Contexta solution validation pipeline.",
    lifespan=lifespan,
)

# CORS — allow the Reflex frontend origin (port 3000) to reach the API.
# When CODESPACE_NAME is available we use the concrete public Codespace origin
# so the Access-Control-Allow-Origin header satisfies the browser for credentialed
# requests (CORS spec forbids "*" with credentials=True; explicit origin is safer).
# Falls back to allow_origins=["*"] for pure local dev where credentials are not
# typically required and there is no proxy rewriting the Origin header.
if _CODESPACE_NAME:
    _cors_origins: list[str] = [
        f"https://{_CODESPACE_NAME}-3000.app.github.dev",
        f"https://{_CODESPACE_NAME}-8001.app.github.dev",
        "http://localhost:3000",
    ]
else:
    _cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Consistent error envelope ─────────────────────────────────────────────────
# All HTTP errors return {"error": "..."} so the frontend toast system has a
# single key to check regardless of status code.
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail)},
    )


# ── Dependency: yields the shared DB connection ───────────────────────────────
async def get_db(request: Request) -> aiosqlite.Connection:
    return request.app.state.db


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness probe — confirms the API process is running."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/projects", response_model=list[ProjectResponse], tags=["projects"])
async def list_projects(
    conn: aiosqlite.Connection = Depends(get_db),
) -> list[ProjectResponse]:
    """Return all projects ordered by insertion time."""
    rows = await repo.list_projects(conn)
    return [
        ProjectResponse(id=r.id, name=r.name, global_tags=r.global_tags)
        for r in rows
    ]


@app.get(
    "/api/projects/{project_id}",
    response_model=ProjectDetailResponse,
    tags=["projects"],
)
async def get_project(
    project_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> ProjectDetailResponse:
    """Return a project with all its versions and node summaries."""
    project = await repo.get_project(conn, project_id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found.",
        )

    versions = await repo.list_versions_for_project(conn, project_id)
    nodes = await repo.list_nodes_for_project(conn, project_id)

    return ProjectDetailResponse(
        id=project.id,
        name=project.name,
        global_tags=project.global_tags,
        versions=[
            VersionResponse(
                id=v.id,
                project_id=v.project_id,
                name=v.name,
                description=v.description,
                created_at=v.created_at,
            )
            for v in versions
        ],
        nodes=[
            NodeSummaryResponse(
                id=n.id,
                project_id=n.project_id,
                parent_id=n.parent_id,
                layer_type=n.layer_type,
                node_name=n.node_name,
                created_at=n.created_at,
                version_tag=n.version_tag,
                version_id=n.version_id,
            )
            for n in nodes
        ],
    )


@app.get(
    "/api/projects/{project_id}/nodes",
    response_model=list[NodeSummaryResponse],
    tags=["nodes"],
)
async def list_nodes(
    project_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> list[NodeSummaryResponse]:
    """Return all node summaries for a project."""
    project = await repo.get_project(conn, project_id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found.",
        )

    nodes = await repo.list_nodes_for_project(conn, project_id)
    return [
        NodeSummaryResponse(
            id=n.id,
            project_id=n.project_id,
            parent_id=n.parent_id,
            layer_type=n.layer_type,
            node_name=n.node_name,
            created_at=n.created_at,
            version_tag=n.version_tag,
            version_id=n.version_id,
        )
        for n in nodes
    ]


@app.get(
    "/api/nodes/{node_id}",
    response_model=NodeDetailResponse,
    tags=["nodes"],
)
async def get_node(
    node_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> NodeDetailResponse:
    """Return full node detail including content and parsed metadata."""
    node = await repo.get_node(conn, node_id)
    if node is None:
        raise HTTPException(
            status_code=404,
            detail=f"Node '{node_id}' not found.",
        )

    # metadata_json is stored as a raw JSON string in the DB; parse it here
    # so the response carries a proper dict rather than an escaped string.
    raw_meta: Any = node.metadata_json
    metadata: Any = raw_meta
    if isinstance(raw_meta, str):
        try:
            metadata = json.loads(raw_meta)
        except json.JSONDecodeError:
            metadata = {}

    return NodeDetailResponse(
        id=node.id,
        project_id=node.project_id,
        parent_id=node.parent_id,
        layer_type=node.layer_type,
        node_name=node.node_name,
        created_at=node.created_at,
        version_tag=node.version_tag,
        version_id=node.version_id,
        content_markdown=node.content_markdown,
        metadata_json=metadata,
    )
