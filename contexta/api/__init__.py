"""
contexta/api/__init__.py — FastAPI application entry point.

Mounts all six route groups under /api and applies the standardised
error-envelope middleware so every HTTP error returns {"error": "..."}.

Run with:
    uvicorn contexta.api:app --host 0.0.0.0 --port 8000

Reflex api_transformer compatibility
--------------------------------------
When this FastAPI app is mounted via ``rx.App(api_transformer=fastapi_app)``
in ``web/web.py``, Reflex wraps it as a sub-ASGI application.  Reflex's own
startup sequence may exercise the Starlette routing layer during compilation
before the ASGI lifespan has fully completed, which can leave ``app.state.db``
uninitialised and cause ``AttributeError`` deep inside ``fastapi/routing.py``.

The lifespan below defends against this with three guarantees:
  1. ``init_database()`` is called exactly once, even if the lifespan fires
     multiple times (re-entrant guard via ``_db_initialised`` flag).
  2. ``app.state.db`` is set *before* ``yield`` so it is always available to
     dependency injection.
  3. ``get_db()`` in ``dependencies.py`` has its own per-request fallback that
     opens an ad-hoc connection when ``app.state.db`` is not yet set — this
     covers the narrow window between process start and lifespan completion.
"""

from __future__ import annotations

import logging
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
from .config import load_api_config
from .routers import admin, artifacts, insights, nodes, projects, proposals, reviews, versions

logger = logging.getLogger(__name__)

# ── DB path resolution ────────────────────────────────────────────────────────
# Sourced from WebAPIConfig so the main app and background pipeline tasks
# (contexta/api/pipeline_bridge.py, invoked via load_api_config().db_path)
# always resolve to the same database file.
_cfg = load_api_config()
_DB_PATH: str = _cfg.db_path

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


# ── Lifespan ──────────────────────────────────────────────────────────────────
# Re-entrant guard: Reflex may construct the ASGI app more than once during
# its hot-reload cycle; we must not open a second connection on top of an
# existing one or we leak file handles and corrupt in-flight transactions.
_db_initialised: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _db_initialised

    # Ensure the parent directory for the DB file exists (supports Docker
    # volume mounts like /app/data/contexta.db on a fresh container).
    db_dir = Path(_DB_PATH).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    if not _db_initialised:
        try:
            app.state.db = await init_database(_DB_PATH)
            _db_initialised = True
            logger.info("Database initialised at %s", _DB_PATH)
        except Exception:
            logger.exception(
                "FATAL: could not initialise database at %s — "
                "API routes will use per-request fallback connections.",
                _DB_PATH,
            )
            # Do NOT raise: let the app start so health probes succeed.
            # get_db() will fall back to per-request connections.
    else:
        # Lifespan fired again (hot-reload): reuse the existing connection.
        logger.debug("Database already initialised, reusing existing connection.")

    yield

    # Teardown: only close when we own the connection.
    if _db_initialised and hasattr(app.state, "db") and app.state.db is not None:
        try:
            await app.state.db.close()
        except Exception:
            logger.debug("Connection already closed during teardown.")
        finally:
            app.state.db = None
            _db_initialised = False


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
app.include_router(nodes.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
