"""
contexta/api/__init__.py — FastAPI application factory.

Exposes a ``create_app(db_path)`` factory so tests can inject an in-memory
SQLite DB.  The module-level ``app`` uses the path from ContextaConfig.

Startup lifecycle:
  1. Open aiosqlite connection (or reuse one injected by tests).
  2. Run DB migrations.
  3. Initialise AdminConfigStore.
  4. Register all sub-routers.
  5. Attach global exception handler.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config_store import AdminConfigStore
from .routers import admin, artifacts, projects, proposals, reviews, versions

logger = logging.getLogger(__name__)


def _register_routers(application: FastAPI) -> None:
    application.include_router(projects.router)
    application.include_router(versions.router)
    application.include_router(reviews.router)
    application.include_router(artifacts.router)
    application.include_router(proposals.router)
    application.include_router(admin.router)


def create_app(db_path: str | None = None) -> FastAPI:
    """
    Build and return a configured FastAPI application.

    Args:
        db_path: SQLite database path.  When None, reads from ContextaConfig.
                 Pass ``":memory:"`` in tests for full isolation.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        # ── Resolve DB path ───────────────────────────────────────────────────
        path = db_path
        if path is None:
            try:
                from ..config import load_config
                cfg = load_config()
                path = cfg.db_path
            except Exception:
                path = "/data/contexta.db"

        # ── Open DB + run migrations ──────────────────────────────────────────
        from ..db.schema import init_database
        conn = await init_database(path)
        application.state.db = conn
        application.state.config_store = AdminConfigStore()

        logger.info("API started — DB: %s", path)
        yield

        # ── Shutdown ──────────────────────────────────────────────────────────
        await conn.close()
        logger.info("API shutdown — DB connection closed.")

    application = FastAPI(
        title="Contexta API",
        description="Solution Acceleration Engine — REST API",
        version="1.0.0",
        lifespan=lifespan,
    )

    _register_routers(application)

    # ── Global exception handler ──────────────────────────────────────────────
    @application.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal server error: {exc}"},
        )

    return application


# Module-level app used by ``uvicorn contexta.api:app``
app = create_app()
