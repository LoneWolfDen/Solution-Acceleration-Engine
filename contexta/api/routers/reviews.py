"""
contexta/api/routers/reviews.py

GET  /api/versions/{version_id}/reviews  — list review jobs for a version
GET  /api/nodes/{node_id}                — full Review_Payload for a review job
POST /api/reviews                        — trigger the real 12-dimension pipeline
                                            (contexta.api.pipeline_bridge, Milestone 4)
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

    # ``commit_exploration_node()`` writes all 12 dimension payloads into
    # metadata_json["dimensions"]; content_markdown only holds the first
    # dimension's payload (used as a schema-guard representative). The full
    # Review_Payload response must aggregate findings across all 12.
    try:
        raw_metadata = node.metadata_json
        metadata = (
            json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
        )
        dimension_dicts = metadata.get("dimensions") or []
        payloads = [
            ReviewNodePayload.model_validate(d) for d in dimension_dicts
        ]
        if not payloads:
            # Fall back to the single payload stored in content_markdown
            # (covers nodes written before Milestone 4 wiring, or tests).
            payloads = [ReviewNodePayload.model_validate_json(node.content_markdown)]
    except Exception:
        logger.warning("Could not parse ReviewNodePayload(s) for node %s", node.id)
        return schemas.ReviewPayloadResponse(
            review_id=job.id,
            project_id=node.project_id,
            version_id=job.version_id,
            status=job.status,
            run_date=node.created_at,
            persona=persona,
        )

    findings: list[schemas.FindingItem] = []
    summary_counts: dict[str, int] = {
        "risks": 0, "constraints": 0, "dependencies": 0,
        "assumptions": 0, "action_items": 0,
    }
    for payload in payloads:
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
    """Return the full Review_Payload for a review job ID or a node UUID.

    Accepts two caller patterns:
    - ``node_id`` is a ``review_jobs.id`` (UUID of the job itself) — used by
      ``_review_row`` in version_detail.py which passes ``review["review_id"]``.
    - ``node_id`` is a ``nodes.id`` (UUID of the committed exploration node) —
      used by ``_node_row`` in version_detail.py and the sidebar which pass
      ``node["id"]`` after the node appears in the project tree.

    Both patterns must return a valid ReviewPayloadResponse.
    """
    # Primary: treat the param as a review_job id.
    job = await api_repo.get_review_job(conn, node_id)
    if job is not None:
        node = None
        if job.node_id:
            node = await db_repo.get_node(conn, job.node_id)
        return _build_review_payload(job, node)

    # Fallback: treat the param as a direct node UUID (called from node_row /
    # sidebar after the pipeline writes the node and the project tree refreshes).
    # Find the review_job that produced this node.
    direct_node = await db_repo.get_node(conn, node_id)
    if direct_node is None:
        raise HTTPException(status_code=404, detail=f"Review or node '{node_id}' not found.")

    # Look up the review_job whose node_id matches.
    cursor = await conn.execute(
        "SELECT * FROM review_jobs WHERE node_id = ? LIMIT 1", (node_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        # Node exists but has no associated review job (e.g. a synthesis node
        # or a TUI-written node).  Return a minimal shell response.
        return schemas.ReviewPayloadResponse(
            review_id=node_id,
            project_id=direct_node.project_id,
            version_id=direct_node.version_id or "",
            status="complete",
            run_date=direct_node.created_at,
            persona="Reviewer",
        )

    from contexta.api.repositories import _row_to_review_job
    job = _row_to_review_job(row)
    return _build_review_payload(job, direct_node)


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
    from contexta.api.pipeline_bridge import run_review_pipeline_task
    db_path = load_api_config().db_path
    background_tasks.add_task(
        run_review_pipeline_task, job.id, db_path, body.backend
    )

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
