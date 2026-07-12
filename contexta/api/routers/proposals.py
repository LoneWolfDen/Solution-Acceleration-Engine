"""
contexta/api/routers/proposals.py

Version-scoped proposal endpoints (Gap 2 + Gap 11):
  POST /api/versions/{version_id}/proposals   — multi-review proposal creation
  GET  /api/versions/{version_id}/proposals   — list proposals for a version

Legacy single-review endpoint (Requirement 2.6):
  POST /api/proposals                         — thin wrapper around version-level logic

Proposal status + acknowledgement (Gap 4):
  GET  /api/proposals/{proposal_id}/status    — poll async status; returns report + alerts
  POST /api/proposals/{proposal_id}/acknowledge — record advisor acknowledgement + resume
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import List

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from contexta.api import repositories as api_repo
from contexta.api import schemas
from contexta.api.dependencies import get_db
from contexta.db import repositories as db_repo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proposals"])


# ── Internal helper ────────────────────────────────────────────────────────────

async def _create_version_proposal(
    version_id: str,
    review_ids: List[str],
    background_tasks: BackgroundTasks,
    conn: aiosqlite.Connection,
) -> schemas.CreateProposalResponse:
    """Core logic shared by the version-scoped endpoint and the legacy wrapper.

    Validates each review_id (must be complete + belong to the version),
    creates the proposal_jobs row, inserts proposal_review_links rows, and
    launches the background synthesis task.

    Gap 2 — Requirements 2.3, 2.4.
    """
    if not review_ids:
        raise HTTPException(
            status_code=422,
            detail="review_ids must contain at least one review ID.",
        )

    # Validate every review_id before writing anything.
    for rid in review_ids:
        review = await api_repo.get_review_job(conn, rid)
        if review is None:
            raise HTTPException(
                status_code=422,
                detail=f"Review '{rid}' does not exist.",
            )
        if review.status != "complete":
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Review '{rid}' is not complete "
                    f"(status='{review.status}'). Only completed reviews can "
                    "feed a proposal."
                ),
            )
        if review.version_id != version_id:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Review '{rid}' belongs to version '{review.version_id}', "
                    f"not '{version_id}'."
                ),
            )

    # Use the first review_id as the backward-compat FK in proposal_jobs.
    job = await api_repo.create_proposal_job(conn, review_job_id=review_ids[0])

    # Insert all review links into the M:N junction table.
    await api_repo.insert_proposal_review_links(conn, job.id, review_ids)

    from contexta.api.config import load_api_config
    from contexta.api.pipeline_bridge import run_proposal_pipeline_task
    db_path = load_api_config().db_path
    background_tasks.add_task(run_proposal_pipeline_task, job.id, db_path)

    logger.info(
        "[INFO] Proposal synthesis triggered — Proposal ID %s "
        "(version=%s, reviews=%s)",
        job.id, version_id, review_ids,
    )
    return schemas.CreateProposalResponse(proposal_id=job.id, status="queued")


# ── Version-scoped endpoints ───────────────────────────────────────────────────

@router.post(
    "/versions/{version_id}/proposals",
    response_model=schemas.CreateProposalResponse,
    status_code=202,
)
async def create_version_proposal(
    version_id: str,
    body: schemas.CreateVersionProposalRequest,
    background_tasks: BackgroundTasks,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.CreateProposalResponse:
    """Trigger multi-review proposal synthesis for a version.

    Gap 2 — Requirement 2.3: accepts an array of ``review_ids``.  Each ID
    must correspond to a completed Review_Job belonging to the specified
    version, otherwise HTTP 422 is returned and no rows are written.
    Returns HTTP 202 immediately; synthesis runs in a background task.
    """
    version = await db_repo.get_version(conn, version_id)
    if version is None:
        raise HTTPException(
            status_code=404, detail=f"Version '{version_id}' not found."
        )

    return await _create_version_proposal(
        version_id=version_id,
        review_ids=body.review_ids,
        background_tasks=background_tasks,
        conn=conn,
    )


@router.get(
    "/versions/{version_id}/proposals",
    response_model=schemas.ProposalListResponse,
)
async def list_version_proposals(
    version_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ProposalListResponse:
    """Return all Proposal_Jobs whose linked reviews belong to a version.

    Gap 11 — Requirement 11.1/11.2: includes proposal_id, status,
    created_at, progress_message, and linked_review_count.  Returns an
    empty list (HTTP 200) when no proposals exist for the version.
    """
    version = await db_repo.get_version(conn, version_id)
    if version is None:
        raise HTTPException(
            status_code=404, detail=f"Version '{version_id}' not found."
        )

    items = await api_repo.list_proposals_for_version(conn, version_id)
    return schemas.ProposalListResponse(
        proposals=[
            schemas.ProposalListItem(
                proposal_id=item.proposal_id,
                status=item.status,
                created_at=item.created_at,
                progress_message=item.progress_message,
                linked_review_count=item.linked_review_count,
                version_id=item.version_id,
            )
            for item in items
        ]
    )


# ── Project-scoped proposal aggregation (Requirement A1 — additive) ───────────

@router.get(
    "/projects/{project_id}/proposals",
    response_model=schemas.ProposalListResponse,
)
async def list_project_proposals(
    project_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ProposalListResponse:
    """Return proposals for every review job belonging to any version under
    this project (Requirement A1).

    This is purely additive: it does NOT remove or weaken the version-scoped
    ``WHERE rj.version_id = ?`` guard in ``list_version_proposals`` above, and
    does not modify ``create_version_proposal``/``list_version_proposals`` or
    their existing 422 validation guards.  Each item includes ``version_id``
    so the UI can group/label proposals by version at the project level.
    """
    project = await db_repo.get_project(conn, project_id)
    if project is None:
        raise HTTPException(
            status_code=404, detail=f"Project '{project_id}' not found."
        )

    items = await api_repo.list_proposals_for_project(conn, project_id)
    return schemas.ProposalListResponse(
        proposals=[
            schemas.ProposalListItem(
                proposal_id=item.proposal_id,
                status=item.status,
                created_at=item.created_at,
                progress_message=item.progress_message,
                linked_review_count=item.linked_review_count,
                version_id=item.version_id,
            )
            for item in items
        ]
    )


# ── Legacy single-review endpoint ──────────────────────────────────────────────

@router.post(
    "/proposals",
    response_model=schemas.CreateProposalResponse,
    status_code=202,
)
async def create_proposal(
    body: schemas.CreateProposalRequest,
    background_tasks: BackgroundTasks,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.CreateProposalResponse:
    """Trigger proposal synthesis from a single completed review.

    Requirement 2.6 — legacy wrapper retained for backward compatibility.
    Delegates to the same internal logic as the version-scoped endpoint
    with a single-element ``review_ids`` list.
    """
    # Resolve the version_id from the review so we can reuse the shared helper.
    review = await api_repo.get_review_job(conn, body.review_id)
    if review is None:
        raise HTTPException(
            status_code=404, detail=f"Review '{body.review_id}' not found."
        )
    if review.status != "complete":
        raise HTTPException(
            status_code=422,
            detail=(
                f"Review '{body.review_id}' is not complete "
                f"(status='{review.status}'). A proposal can only be "
                "generated from a completed review."
            ),
        )

    return await _create_version_proposal(
        version_id=review.version_id,
        review_ids=[body.review_id],
        background_tasks=background_tasks,
        conn=conn,
    )


# ── Proposal status + report ───────────────────────────────────────────────────

@router.get(
    "/proposals/{proposal_id}/status",
    response_model=schemas.ProposalStatusResponse,
)
async def get_proposal_status(
    proposal_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ProposalStatusResponse:
    """Poll proposal synthesis status.

    When status is ``awaiting_acknowledgement`` the ``alerts`` list is
    populated with the Proactive Advisor findings that must be reviewed
    before synthesis can proceed (Gap 4 — Requirement 4.2).

    When status is ``complete`` the full ``ReconciliationReport`` is
    returned in the ``report`` field.
    """
    job = await api_repo.get_proposal_job(conn, proposal_id)
    if job is None:
        raise HTTPException(
            status_code=404, detail=f"Proposal '{proposal_id}' not found."
        )

    # Deserialise the metadata blob for alerts and report extraction.
    try:
        metadata: dict = json.loads(job.metadata_json) if job.metadata_json else {}
    except (json.JSONDecodeError, TypeError):
        metadata = {}

    # Gap 4 — surface advisory alerts when present.
    alerts: list[schemas.AdvisoryAlertItem] | None = None
    raw_alerts = metadata.get("alerts")
    if raw_alerts:
        alerts = [
            schemas.AdvisoryAlertItem(
                pattern=a.get("pattern", ""),
                tag_combination=a.get("tag_combination", []),
                frequency_count=a.get("frequency_count", 0),
                advisory_text=a.get("advisory_text", ""),
            )
            for a in raw_alerts
        ]

    # Reconstruct the ReconciliationReport when synthesis is complete.
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
        alerts=alerts,
    )


# ── Advisor acknowledgement (Gap 4) ───────────────────────────────────────────

@router.post(
    "/proposals/{proposal_id}/acknowledge",
    response_model=schemas.AcknowledgeResponse,
)
async def acknowledge_proposal(
    proposal_id: str,
    background_tasks: BackgroundTasks,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.AcknowledgeResponse:
    """Record advisor acknowledgement and resume synthesis pipeline.

    Gap 4 — Requirements 4.4/4.7: records an ISO-8601 UTC timestamp in
    ``metadata_json["acknowledged_at"]`` for audit purposes, then
    re-launches the proposal synthesis background task.  The pipeline
    bridge skips advisor re-evaluation when ``acknowledged_at`` is present.
    """
    from datetime import datetime, timezone

    job = await api_repo.get_proposal_job(conn, proposal_id)
    if job is None:
        raise HTTPException(
            status_code=404, detail=f"Proposal '{proposal_id}' not found."
        )
    if job.status != "awaiting_acknowledgement":
        raise HTTPException(
            status_code=422,
            detail=(
                f"Proposal '{proposal_id}' is not awaiting acknowledgement "
                f"(status='{job.status}')."
            ),
        )

    # Stamp the acknowledgement timestamp into metadata.
    try:
        metadata: dict = json.loads(job.metadata_json) if job.metadata_json else {}
    except (json.JSONDecodeError, TypeError):
        metadata = {}

    metadata["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
    await api_repo.update_proposal_job_status(
        conn,
        proposal_id,
        status="queued",
        progress_message="Acknowledged — re-queueing synthesis…",
    )
    # Persist the updated metadata separately via the node metadata helper.
    await conn.execute(
        "UPDATE proposal_jobs SET metadata_json = ? WHERE id = ?",
        (json.dumps(metadata), proposal_id),
    )
    await conn.commit()

    from contexta.api.config import load_api_config
    from contexta.api.pipeline_bridge import run_proposal_pipeline_task
    db_path = load_api_config().db_path
    background_tasks.add_task(run_proposal_pipeline_task, proposal_id, db_path)

    logger.info(
        "[INFO] Proposal '%s' acknowledged — synthesis re-queued.", proposal_id
    )
    return schemas.AcknowledgeResponse(status="running")
