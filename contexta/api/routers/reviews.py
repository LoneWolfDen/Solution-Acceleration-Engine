"""
contexta/api/routers/reviews.py

GET  /api/versions/{version_id}/reviews
GET  /api/nodes/{node_id}
POST /api/reviews
GET  /api/reviews/{review_id}/status
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ...db import repositories as repo
from ..dependencies import get_db
from ..schemas import (
    FindingResponse,
    ReviewCreateRequest,
    ReviewCreateResponse,
    ReviewListResponse,
    ReviewPayloadResponse,
    ReviewStatusResponse,
    ReviewSummary,
    ReviewSummaryPayload,
)

router = APIRouter(tags=["reviews"])

# In-memory review status store keyed by review_id.
# Survives within a single process; resets on restart (acceptable for MVP).
_review_status: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Background stub ───────────────────────────────────────────────────────────


async def _run_review_stub(review_id: str, db_path: str) -> None:
    """Stub background task — logs intent, marks review complete.

    Real pipeline wiring is deferred to Milestone 4.
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.info("STUB: pipeline not yet wired for review_id=%s", review_id)
    _review_status[review_id]["status"] = "complete"
    _review_status[review_id]["progress_message"] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/api/versions/{version_id}/reviews", response_model=ReviewListResponse
)
async def list_reviews(
    version_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ReviewListResponse:
    version = await repo.get_version(db, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found.")

    cursor = await db.execute(
        "SELECT id, node_name, metadata_json, created_at FROM nodes "
        "WHERE version_id = ? AND layer_type = 'synthesis' ORDER BY created_at",
        (version_id,),
    )
    rows = await cursor.fetchall()

    reviews: list[ReviewSummary] = []
    for row in rows:
        meta = json.loads(row["metadata_json"] or "{}")
        status = _review_status.get(row["id"], {}).get("status", meta.get("status", "complete"))
        reviews.append(
            ReviewSummary(
                review_id=row["id"],
                run_date=row["created_at"],
                status=status,
                persona=meta.get("persona", ""),
            )
        )
    return ReviewListResponse(reviews=reviews, error=None)


@router.get("/api/nodes/{node_id}", response_model=ReviewPayloadResponse)
async def get_node(
    node_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ReviewPayloadResponse:
    node = await repo.get_node(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")

    meta_raw = node.metadata_json
    meta: dict = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw

    # Parse findings from content_markdown if it contains a ReviewNodePayload.
    findings: list[FindingResponse] = []
    try:
        if node.content_markdown:
            payload_data = json.loads(node.content_markdown)
            for i, f in enumerate(payload_data.get("findings", [])):
                citations = f.get("citations", [])
                citation_text = (
                    citations[0].get("excerpt", "") if citations else ""
                )
                findings.append(
                    FindingResponse(
                        finding_id=str(i),
                        type=f.get("dimension", ""),
                        severity=f.get("confidence", ""),
                        text=f.get("summary", ""),
                        source_artifact=citations[0].get("file_path", "") if citations else "",
                        citation=citation_text,
                    )
                )
    except (json.JSONDecodeError, AttributeError):
        pass

    # Build summary counts from findings.
    summary = ReviewSummaryPayload(
        risks=sum(1 for f in findings if "risk" in f.type.lower()),
        constraints=sum(1 for f in findings if "constraint" in f.type.lower() or "nfr" in f.type.lower()),
        dependencies=0,
        assumptions=0,
        action_items=len(findings),
    )

    status = _review_status.get(node_id, {}).get("status", meta.get("status", "complete"))

    return ReviewPayloadResponse(
        review_id=node.id,
        project_id=node.project_id,
        version_id=node.version_id,
        status=status,
        run_date=node.created_at,
        persona=meta.get("persona", ""),
        findings=findings,
        summary=summary,
        error=None,
    )


@router.post("/api/reviews", response_model=ReviewCreateResponse, status_code=202)
async def create_review(
    body: ReviewCreateRequest,
    background_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db),
) -> ReviewCreateResponse:
    version = await repo.get_version(db, body.version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version '{body.version_id}' not found.")

    review_id = str(uuid.uuid4())
    now = _now_iso()
    persona = ", ".join(body.persona_roles) if body.persona_roles else "default"
    meta = {
        "persona": persona,
        "persona_roles": body.persona_roles,
        "context": body.context,
        "status": "queued",
    }

    await db.execute(
        """
        INSERT INTO nodes
            (id, project_id, parent_id, layer_type, node_name,
             metadata_json, content_markdown, created_at, version_tag, version_id)
        VALUES (?, ?, NULL, 'synthesis', ?, ?, '', ?, NULL, ?)
        """,
        (
            review_id,
            version.project_id,
            f"Review — {now}",
            json.dumps(meta),
            now,
            body.version_id,
        ),
    )
    await db.commit()

    _review_status[review_id] = {
        "status": "queued",
        "progress_message": "Review queued.",
    }

    # Get db_path from the node row we just inserted (path not stored here).
    # The stub just needs the review_id; pass an empty string for db_path.
    background_tasks.add_task(_run_review_stub, review_id, "")

    return ReviewCreateResponse(review_id=review_id, status="queued", error=None)


@router.get("/api/reviews/{review_id}/status", response_model=ReviewStatusResponse)
async def get_review_status(
    review_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ReviewStatusResponse:
    node = await repo.get_node(db, review_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found.")

    state = _review_status.get(review_id, {})
    status = state.get("status", "complete")
    progress = state.get("progress_message")

    return ReviewStatusResponse(
        review_id=review_id,
        status=status,
        progress_message=progress,
        error=None,
    )
