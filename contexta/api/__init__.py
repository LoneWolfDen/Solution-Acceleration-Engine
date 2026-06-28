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
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..db.schema import init_database
from .routers import admin, artifacts, projects, proposals, reviews, versions

# ── DB path resolution ────────────────────────────────────────────────────────
_PROJECT_ROOT: Path = Path(__file__).parents[2]
_DEFAULT_DB_PATH: str = str(_PROJECT_ROOT / "data" / "contexta.db")
_DB_PATH: str = os.environ.get("CONTEXTA_DB_PATH", _DEFAULT_DB_PATH)

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


# ── Lifespan: single shared connection for the process lifetime ───────────────
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Consistent error envelope ─────────────────────────────────────────────────
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Return {"error": "..."} on every HTTP exception so the frontend
    toast system has a single key to check."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all: return 500 with error envelope on any unhandled exception."""
    return JSONResponse(
        status_code=500,
        content={"error": f"Internal server error: {exc}"},
    )


# ── Health probe ──────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0", "error": None}


# ── Mount routers ─────────────────────────────────────────────────────────────
app.include_router(projects.router, prefix="/api")
app.include_router(versions.router, prefix="/api")
app.include_router(artifacts.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(proposals.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
