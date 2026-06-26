"""
contexta/api/routers/reviews.py

GET  /api/versions/{version_id}/reviews  — list review jobs for a version
GET  /api/nodes/{node_id}                — full Review_Payload for a review job
POST /api/reviews                        — trigger pipeline (stub with logging)
GET  /api/reviews/{review_id}/status     — poll async status
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from contexta.api import repositories as api_repo
from contexta.api import schemas
from contexta.api.dependencies import get_db
from contexta.db import repositories as db_repo
from contexta.models.enums import ReviewDimensionEnum

logger = logging.getLogger(__name__)
router = APIRouter(tags=["reviews"])

# ─── Dimension → summary category mapping ─────────────────────────────────────

_DIMENSION_CATEGORY: dict[str, str] = {
    ReviewDimensionEnum.RISK: "risks",
    ReviewDimensionEnum.SCOPE: "constraints",
    ReviewDimensionEnum.OWNERSHIP: "constraints",
    ReviewDimensionEnum.COMMERCIAL: "constraints",
    ReviewDimensionEnum.ARCHITECTURE: "dependencies",
    ReviewDimensionEnum.NFR: "dependencies",
    ReviewDimensionEnum.DELIVERY: "action_items",
    ReviewDimensionEnum.TIMELINE: "action_items",
    ReviewDimensionEnum.RESOURCE: "action_items",
    ReviewDimensionEnum.INTENT: "assumptions",
    ReviewDimensionEnum.LANGUAGE: "assumptions",
    ReviewDimensionEnum.CONSISTENCY: "assumptions",
}

_CONFIDENCE_SEVERITY: dict[str, str] = {
    "RED": "HIGH",
    "AMBER": "MEDIUM",
    "GREEN": "LOW",
}


def _build_review_payload(job: "api_repo.ReviewJobRow", node: Optional[object]) -> schemas.ReviewPayloadResponse:
    """Map a ReviewJobRow (+ optional parsed node) to ReviewPayloadResponse."""
    persona = job.persona_roles[0] if job.persona_roles else "Unknown"

    if node is None or job.status != "complete":
        return schemas.ReviewPayloadResponse(
            review_id=job.id,
            project_id="",
            version_id=job.version_id,
            status=job.status,
            run_date=job.created_at,
            persona=persona,
        )

    from contexta.models.payloads import ReviewNodePayload

    try:
        payload = ReviewNodePayload.model_validate_json(node.content_markdown)
    except Exception:
        logger.warning("Could not parse ReviewNodePayload for node %s", node.id)
        return schemas.ReviewPayloadResponse(
            review_id=job.id,
            project_id=node.project_id,
            version_id=job.version_id,
            status=job.status,
            run_date=node.created_at,
            persona=persona,
        )

    findings: list[schemas.FindingItem] = []
    for f in payload.findings:
        source = f.citations[0].file_path if f.citations else "unknown"
        excerpt = f.citations[0].excerpt if f.citations else ""
        findings.append(
            schemas.FindingItem(
                finding_id=str(uuid.uuid4()),
                type=f.dimension.value,
                severity=_CONFIDENCE_SEVERITY.get(f.confidence.value, "MEDIUM"),
                text=f.summary,
                source_artifact=source,
                citation=excerpt,
            )
        )

    summary_counts: dict[str, int] = {
        "risks": 0, "constraints": 0, "dependencies": 0,
        "assumptions": 0, "action_items": 0,
    }
    for f in payload.findings:
        cat = _DIMENSION_CATEGORY.get(f.dimension, "assumptions")
        summary_counts[cat] += 1

    return schemas.ReviewPayloadResponse(
        review_id=job.id,
        project_id=node.project_id,
        version_id=job.version_id,
        status=job.status,
        run_date=node.created_at,
        persona=persona,
        findings=findings,
        summary=schemas.FindingsSummary(**summary_counts),
    )


# ─── Stub background task ─────────────────────────────────────────────────────

async def _stub_pipeline_task(review_id: str, db_path: str) -> None:
    """
    Milestone 1 stub — logs pipeline trigger.  No LLM calls are made.
    Sets status to 'complete' immediately so polling returns a terminal state.
    Wired to the real pipeline in Milestone 4.
    """
    import aiosqlite as _aiosqlite
    from contexta.db.schema import init_database

    logger.info("[INFO] Pipeline review triggered for Review ID %s", review_id)
    logger.info("[STUB] Pipeline not yet wired — marking review %s as complete.", review_id)

    conn = await init_database(db_path)
    try:
        await api_repo.update_review_job_status(
            conn, review_id, "complete",
            progress_message="Stub complete — pipeline wiring pending (Milestone 4).",
        )
    finally:
        await conn.close()


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get(
    "/versions/{version_id}/reviews",
    response_model=schemas.ReviewListResponse,
)
async def list_reviews(
    version_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ReviewListResponse:
    version = await db_repo.get_version(conn, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")

    jobs = await api_repo.list_review_jobs_for_version(conn, version_id)
    return schemas.ReviewListResponse(
        reviews=[
            schemas.ReviewItem(
                review_id=j.id,
                run_date=j.created_at,
                status=j.status,
                persona=j.persona_roles[0] if j.persona_roles else "Unknown",
            )
            for j in jobs
        ]
    )


@router.get("/nodes/{node_id}", response_model=schemas.ReviewPayloadResponse)
async def get_review_payload(
    node_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ReviewPayloadResponse:
    """Return the full Review_Payload for a review job ID."""
    job = await api_repo.get_review_job(conn, node_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Review '{node_id}' not found.")

    node = None
    if job.node_id:
        node = await db_repo.get_node(conn, job.node_id)

    return _build_review_payload(job, node)


@router.post("/reviews", response_model=schemas.CreateReviewResponse, status_code=202)
async def create_review(
    body: schemas.CreateReviewRequest,
    background_tasks: BackgroundTasks,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.CreateReviewResponse:
    """Trigger the review pipeline.  Returns immediately with status='queued'."""
    version = await db_repo.get_version(conn, body.version_id)
    if version is None:
        raise HTTPException(
            status_code=404, detail=f"Version '{body.version_id}' not found."
        )
    if not body.persona_roles:
        raise HTTPException(
            status_code=422, detail="persona_roles must contain at least one role."
        )

    job = await api_repo.create_review_job(
        conn, body.version_id, body.persona_roles, body.context
    )

    from contexta.api.config import load_api_config
    db_path = load_api_config().db_path
    background_tasks.add_task(_stub_pipeline_task, job.id, db_path)

    logger.info(
        "[INFO] Pipeline review triggered for Review ID %s (version=%s, roles=%s)",
        job.id, body.version_id, body.persona_roles,
    )
    return schemas.CreateReviewResponse(review_id=job.id, status="queued")


@router.get("/reviews/{review_id}/status", response_model=schemas.ReviewStatusResponse)
async def get_review_status(
    review_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ReviewStatusResponse:
    job = await api_repo.get_review_job(conn, review_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found.")
    return schemas.ReviewStatusResponse(
        review_id=job.id,
        status=job.status,
        progress_message=job.progress_message,
    )
