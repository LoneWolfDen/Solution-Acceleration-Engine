"""
contexta/api/routers/proposals.py

POST /api/proposals                        — trigger synthesis (stub with logging)
GET  /api/proposals/{proposal_id}/status   — poll async status
"""

from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from contexta.api import repositories as api_repo
from contexta.api import schemas
from contexta.api.dependencies import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proposals"])


async def _stub_synthesis_task(proposal_id: str, db_path: str) -> None:
    """
    Milestone 1 stub — logs synthesis trigger.  No LLM calls are made.
    Sets status to 'complete' immediately.  Wired to the real synthesis
    engine in Milestone 4.
    """
    from contexta.db.schema import init_database

    logger.info("[INFO] Proposal synthesis triggered for Proposal ID %s", proposal_id)
    logger.info("[STUB] Synthesis not yet wired — marking proposal %s as complete.", proposal_id)

    conn = await init_database(db_path)
    try:
        await api_repo.update_proposal_job_status(
            conn, proposal_id, "complete",
            progress_message="Stub complete — synthesis wiring pending (Milestone 4).",
        )
    finally:
        await conn.close()


@router.post("/proposals", response_model=schemas.CreateProposalResponse, status_code=202)
async def create_proposal(
    body: schemas.CreateProposalRequest,
    background_tasks: BackgroundTasks,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.CreateProposalResponse:
    """Trigger proposal synthesis for a completed review.  Returns immediately."""
    review = await api_repo.get_review_job(conn, body.review_id)
    if review is None:
        raise HTTPException(
            status_code=404, detail=f"Review '{body.review_id}' not found."
        )
    if review.status != "complete":
        raise HTTPException(
            status_code=422,
            detail=f"Review '{body.review_id}' is not complete (status='{review.status}'). "
                   "A proposal can only be generated from a completed review.",
        )

    job = await api_repo.create_proposal_job(conn, body.review_id)

    from contexta.api.config import load_api_config
    db_path = load_api_config().db_path
    background_tasks.add_task(_stub_synthesis_task, job.id, db_path)

    logger.info(
        "[INFO] Proposal synthesis triggered for Proposal ID %s (review=%s)",
        job.id, body.review_id,
    )
    return schemas.CreateProposalResponse(proposal_id=job.id, status="queued")


@router.get(
    "/proposals/{proposal_id}/status",
    response_model=schemas.ProposalStatusResponse,
)
async def get_proposal_status(
    proposal_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ProposalStatusResponse:
    job = await api_repo.get_proposal_job(conn, proposal_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")
    return schemas.ProposalStatusResponse(
        proposal_id=job.id,
        status=job.status,
        progress_message=job.progress_message,
    )
