"""
contexta/api/__init__.py — FastAPI application entry point.

Mounts all six route groups under /api and applies the standardised
error-envelope middleware so every HTTP error returns {"error": "..."}.

Run with:
    uvicorn contexta.api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..db.schema import init_database
from .config import load_api_config
from .routers import admin, artifacts, projects, proposals, reviews, versions

# ── DB path resolution ────────────────────────────────────────────────────────
# Sourced from WebAPIConfig so the main app and background pipeline tasks
# (contexta/api/pipeline_bridge.py, invoked via load_api_config().db_path)
# always resolve to the same database file.
_DB_PATH: str = load_api_config().db_path

# ── CORS origin resolution ────────────────────────────────────────────────────
_CODESPACE_NAME: str = os.environ.get("CODESPACE_NAME", "")

if _CODESPACE_NAME:
    _cors_origins: list[str] = [
        f"https://{_CODESPACE_NAME}-3000.app.github.dev",
        f"https://{_CODESPACE_NAME}-8001.app.github.dev",
        "http://localhost:3000",
        "http://localhost:8001",
    ]
else:
    _cors_origins = ["*"]


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.db = await init_database(_DB_PATH)
    yield
    await app.state.db.close()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Contexta API",
    version="0.1.0",
    description=(
        "REST API for the Solution Acceleration Engine. "
        "Every response carries an `error` field: null on success, "
        "a human-readable string on failure."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=(_cors_origins != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Consistent error envelope ─────────────────────────────────────────────────
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": f"Internal server error: {exc}"},
    )


# ── Health probe ──────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0", "error": None}


# ── Mount all routers ─────────────────────────────────────────────────────────
app.include_router(projects.router, prefix="/api")
app.include_router(versions.router, prefix="/api")
app.include_router(artifacts.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(proposals.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
