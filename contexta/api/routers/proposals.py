"""
contexta/api/routers/proposals.py

POST /api/proposals                        — trigger Layer 2 synthesis
                                              (contexta.api.pipeline_bridge, Milestone 4)
GET  /api/proposals/{proposal_id}/status   — poll async status; returns the
                                              ReconciliationReport once complete
"""

from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from contexta.api import repositories as api_repo
from contexta.api import schemas
from contexta.api.dependencies import get_db
from contexta.db import repositories as db_repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proposals"])


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
    from contexta.api.pipeline_bridge import run_proposal_pipeline_task
    db_path = load_api_config().db_path
    background_tasks.add_task(run_proposal_pipeline_task, job.id, db_path)

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

    report: dict | None = None
    if job.status == "complete" and job.node_id:
        node = await db_repo.get_node(conn, job.node_id)
        if node is not None:
            try:
                from contexta.llm.models import ReconciliationReport

                report = ReconciliationReport.model_validate_json(
                    node.content_markdown
                ).model_dump()
            except Exception:
                logger.warning(
                    "Could not parse ReconciliationReport for node %s", node.id
                )

    return schemas.ProposalStatusResponse(
        proposal_id=job.id,
        status=job.status,
        progress_message=job.progress_message,
        report=report,
    )
