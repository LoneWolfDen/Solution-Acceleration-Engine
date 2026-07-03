"""POST /api/proposals and GET /api/proposals/{proposal_id}/status."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..dependencies import get_db
from ..schemas import (
    ProposalCreateRequest,
    ProposalCreateResponse,
    ProposalStatusResponse,
)

router = APIRouter(tags=["proposals"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


async def _run_proposal_stub(proposal_id: str, db_path: str) -> None:
    """Stub proposal generator — marks proposal complete immediately."""
    import os
    from ...db.schema import init_database

    path = os.environ.get("CONTEXTA_DB_PATH", db_path)
    conn = await init_database(path)
    try:
        await conn.execute(
            "UPDATE proposals SET status = 'complete', progress_message = 'Proposal stub completed.' WHERE id = ?",
            (proposal_id,),
        )
        await conn.commit()
    except Exception:
        try:
            await conn.execute(
                "UPDATE proposals SET status = 'failed', error_message = 'Stub proposal error.' WHERE id = ?",
                (proposal_id,),
            )
            await conn.commit()
        except Exception:
            pass
    finally:
        await conn.close()


@router.post("/proposals", response_model=ProposalCreateResponse, status_code=202)
async def create_proposal(
    body: ProposalCreateRequest,
    background_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db),
) -> ProposalCreateResponse:
    """Enqueue a new proposal generation job and return immediately."""
    import os

    cursor = await db.execute(
        "SELECT id FROM reviews WHERE id = ?", (body.review_id,)
    )
    if await cursor.fetchone() is None:
        raise HTTPException(
            status_code=404,
            detail=f"Review '{body.review_id}' not found.",
        )

    proposal_id = _new_id()
    now = _now_iso()

    await db.execute(
        "INSERT INTO proposals (id, review_id, status, created_at) VALUES (?, ?, 'queued', ?)",
        (proposal_id, body.review_id, now),
    )
    await db.commit()

    db_path = os.environ.get("CONTEXTA_DB_PATH", "/data/contexta.db")
    background_tasks.add_task(_run_proposal_stub, proposal_id, db_path)

    return ProposalCreateResponse(proposal_id=proposal_id, status="queued", error=None)


@router.get("/proposals/{proposal_id}/status", response_model=ProposalStatusResponse)
async def get_proposal_status(
    proposal_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ProposalStatusResponse:
    """Poll the current status of an async proposal job."""
    cursor = await db.execute(
        "SELECT id, status, progress_message, error_message FROM proposals WHERE id = ?",
        (proposal_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Proposal '{proposal_id}' not found."
        )

    error_field = row["error_message"] if row["status"] == "failed" else None

    return ProposalStatusResponse(
        proposal_id=row["id"],
        status=row["status"],
        progress_message=row["progress_message"],
        error=error_field,
    )
