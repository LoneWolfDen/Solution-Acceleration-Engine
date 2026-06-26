"""
contexta/api/__init__.py — FastAPI application factory.

Entry point:  uvicorn contexta.api:app --host 0.0.0.0 --port 8000

Architecture:
  - Single aiosqlite connection opened at startup via lifespan and stored on
    app.state.db.  All route handlers receive it via Depends(get_db).
  - Global exception handlers ensure every error response carries the
    standardised { error: str } envelope, never FastAPI's default { detail }.
  - All routers are mounted under /api for clean namespacing.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from contexta.api.config import load_api_config
from contexta.db.schema import init_database

logger = logging.getLogger(__name__)


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Open the DB connection on startup; close it on shutdown."""
    config = load_api_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("SAE Web API starting — DB: %s", config.db_path)
    conn = await init_database(config.db_path)
    application.state.db = conn
    try:
        yield
    finally:
        logger.info("SAE Web API shutting down — closing DB connection.")
        await conn.close()


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Solution Acceleration Engine API",
    version="1.0.0",
    description=(
        "REST API for the Solution-Acceleration-Engine web UI. "
        "Every response includes an `error` field: null on success, "
        "a human-readable string on failure."
    ),
    lifespan=lifespan,
)


# ─── Exception handlers ───────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"error": f"Internal server error: {type(exc).__name__}: {exc}"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    messages = "; ".join(
        f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}" for e in exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content={"error": f"Validation error: {messages}"},
    )


# HTTPException handler — converts { detail } → { error }
from fastapi.exceptions import HTTPException as FastAPIHTTPException  # noqa: E402


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(
    request: Request, exc: FastAPIHTTPException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


# ─── Routers ──────────────────────────────────────────────────────────────────

from contexta.api.routers import (  # noqa: E402
    admin,
    artifacts,
    projects,
    proposals,
    reviews,
    versions,
)

app.include_router(projects.router, prefix="/api")
app.include_router(versions.router, prefix="/api")
app.include_router(artifacts.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(proposals.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {"status": "ok", "service": "Solution Acceleration Engine API", "error": None}
