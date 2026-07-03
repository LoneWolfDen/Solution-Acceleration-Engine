"""contexta.api — FastAPI application.

Mount point:
    The FastAPI ``app`` object exported from this module is the entry point
    used by uvicorn::

        uvicorn contexta.api:app --reload

Routers registered:
    /api/projects   — project CRUD
    /api/versions   — version CRUD
    /api/reviews    — review scheduling + status polling
    /api/artifacts  — artifact ingestion + triage
    /api/proposals  — proposal generation + status polling
    /api/admin      — health check + LLM config management
    /api/nodes      — direct node fetch (used by review detail pane)
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .routers import admin, artifacts, nodes, projects, proposals, reviews, versions

app = FastAPI(
    title="Solution Acceleration Engine API",
    description="Deterministic solution-review pipeline — REST API",
    version="1.0.0",
)

# ── Global error handler ──────────────────────────────────────────────────────


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a structured error envelope for any unhandled exception."""
    return JSONResponse(
        status_code=500,
        content={"error": f"Internal server error: {exc}"},
    )


# ── Router registration ───────────────────────────────────────────────────────

app.include_router(projects.router, prefix="/api")
app.include_router(versions.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(artifacts.router, prefix="/api")
app.include_router(proposals.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(nodes.router, prefix="/api")
