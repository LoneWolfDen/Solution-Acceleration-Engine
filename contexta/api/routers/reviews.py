"""Reviews: POST /api/reviews, GET /api/versions/{id}/reviews, GET /api/reviews/{id}/status."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..dependencies import get_db
from ..schemas import (
    ReviewCreateRequest,
    ReviewCreateResponse,
    ReviewListResponse,
    ReviewStatusResponse,
    ReviewSummary,
)

router = APIRouter(tags=["reviews"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Background task stub ──────────────────────────────────────────────────────
# The real pipeline is wired in Milestone 4.  This stub updates the review
# status to "complete" immediately so the polling endpoint has a terminal state
# to return.  Tests mock this function to control status transitions.

async def _run_pipeline_stub(review_id: str, db_path: str) -> None:
    """Stub pipeline: connects its own DB session and marks review complete."""
    import os
    from ...db.schema import init_database

    path = os.environ.get("CONTEXTA_DB_PATH", db_path)
    conn = await init_database(path)
    try:
        await conn.execute(
            "UPDATE reviews SET status = 'complete', progress_message = 'Pipeline stub completed.' WHERE id = ?",
            (review_id,),
        )
        await conn.commit()
    except Exception:
        try:
            await conn.execute(
                "UPDATE reviews SET status = 'failed', error_message = 'Stub pipeline error.' WHERE id = ?",
                (review_id,),
            )
            await conn.commit()
        except Exception:
            pass
    finally:
        await conn.close()


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/versions/{version_id}/reviews", response_model=ReviewListResponse)
async def list_reviews(
    version_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ReviewListResponse:
    """Return all reviews for a version."""
    cursor = await db.execute("SELECT id FROM versions WHERE id = ?", (version_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")

    cursor = await db.execute(
        "SELECT id, run_date, status, persona_roles FROM reviews WHERE version_id = ? ORDER BY run_date",
        (version_id,),
    )
    rows = await cursor.fetchall()
    reviews = [
        ReviewSummary(
            review_id=row["id"],
            run_date=row["run_date"],
            status=row["status"],
            persona=row["persona_roles"],
        )
        for row in rows
    ]
    return ReviewListResponse(reviews=reviews, error=None)


@router.post("/reviews", response_model=ReviewCreateResponse, status_code=202)
async def create_review(
    body: ReviewCreateRequest,
    background_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db),
) -> ReviewCreateResponse:
    """Enqueue a new review and return immediately with status 'queued'."""
    cursor = await db.execute("SELECT id FROM versions WHERE id = ?", (body.version_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{body.version_id}' not found.",
        )

    import json
    import os

    review_id = _new_id()
    now = _now_iso()
    persona_str = json.dumps(body.persona_roles)

    await db.execute(
        """
        INSERT INTO reviews (id, version_id, persona_roles, context, status, run_date)
        VALUES (?, ?, ?, ?, 'queued', ?)
        """,
        (review_id, body.version_id, persona_str, body.context, now),
    )
    await db.commit()

    db_path = os.environ.get("CONTEXTA_DB_PATH", "/data/contexta.db")
    background_tasks.add_task(_run_pipeline_stub, review_id, db_path)

    return ReviewCreateResponse(review_id=review_id, status="queued", error=None)


@router.get("/reviews/{review_id}/status", response_model=ReviewStatusResponse)
async def get_review_status(
    review_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ReviewStatusResponse:
    """Poll the current status of an async review job."""
    cursor = await db.execute(
        "SELECT id, status, progress_message, error_message FROM reviews WHERE id = ?",
        (review_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found.")

    error_field = row["error_message"] if row["status"] == "failed" else None

    return ReviewStatusResponse(
        review_id=row["id"],
        status=row["status"],
        progress_message=row["progress_message"],
        error=error_field,
    )
