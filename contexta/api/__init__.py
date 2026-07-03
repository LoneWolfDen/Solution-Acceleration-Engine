"""
contexta/api/__init__.py — FastAPI application factory and route definitions.

Exports:
    app  — the FastAPI application instance, referenced by uvicorn as
           ``contexta.api:app``.

Routes:
    POST /api/projects  — create a new project, returns 201 + CreateProjectResponse.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Optional

import aiosqlite
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..db.repositories import create_project, list_projects
from ..db.schema import init_database
from .config import load_api_config


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    """Request body for POST /api/projects."""

    name: str = Field(..., min_length=1, max_length=255, description="Human-readable project name.")
    global_tags: List[str] = Field(default_factory=list, description="Optional list of tag strings scoped to the project.")


class CreateProjectResponse(BaseModel):
    """Response body for a successfully created project."""

    id: str = Field(..., description="UUID of the newly created project.")
    name: str = Field(..., description="Project name as stored.")
    global_tags: List[str] = Field(..., description="Tags attached to the project.")


# ─────────────────────────────────────────────────────────────────────────────
# Application lifespan — open / close the DB connection
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the SQLite connection on startup and close it on shutdown."""
    cfg = load_api_config()
    conn: aiosqlite.Connection = await init_database(cfg.db_path)
    app.state.db = conn
    try:
        yield
    finally:
        await conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Contexta API",
    version="0.1.0",
    description="REST interface for the Contexta solution-validation pipeline.",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/api/projects",
    response_model=CreateProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def post_create_project(
    body: CreateProjectRequest,
    request: Request,
) -> CreateProjectResponse:
    """
    Create a new project and return its persisted representation.

    - **name**: required, 1–255 characters.
    - **global_tags**: optional list of strings; defaults to empty list.

    Returns **201 Created** with the full project record on success.
    Returns **422 Unprocessable Entity** if the request body fails validation.
    Returns **500 Internal Server Error** if the database write fails.
    """
    conn: aiosqlite.Connection = request.app.state.db
    try:
        row = await create_project(conn, body.name, body.global_tags)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {exc}",
        ) from exc

    return CreateProjectResponse(
        id=row.id,
        name=row.name,
        global_tags=row.global_tags,
    )
