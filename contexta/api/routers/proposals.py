"""
contexta/api/routers/proposals.py

POST /api/proposals
GET  /api/proposals/{proposal_id}/status
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
    ProposalCreateRequest,
    ProposalCreateResponse,
    ProposalStatusResponse,
)

router = APIRouter(prefix="/api/proposals", tags=["proposals"])

# In-memory proposal status store keyed by proposal_id.
_proposal_status: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Background stub ───────────────────────────────────────────────────────────


async def _run_proposal_stub(proposal_id: str) -> None:
    """Stub background task — marks proposal complete without LLM calls."""
    import logging

    logger = logging.getLogger(__name__)
    logger.info("STUB: pipeline not yet wired for proposal_id=%s", proposal_id)
    _proposal_status[proposal_id]["status"] = "complete"
    _proposal_status[proposal_id]["progress_message"] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", response_model=ProposalCreateResponse, status_code=202)
async def create_proposal(
    body: ProposalCreateRequest,
    background_tasks: BackgroundTasks,
    db: aiosqlite.Connection = Depends(get_db),
) -> ProposalCreateResponse:
    # The review_id must reference an existing synthesis node.
    review_node = await repo.get_node(db, body.review_id)
    if review_node is None:
        raise HTTPException(
            status_code=404, detail=f"Review '{body.review_id}' not found."
        )

    proposal_id = str(uuid.uuid4())
    now = _now_iso()
    meta = {
        "review_id": body.review_id,
        "status": "queued",
        "type": "proposal",
    }

    await db.execute(
        """
        INSERT INTO nodes
            (id, project_id, parent_id, layer_type, node_name,
             metadata_json, content_markdown, created_at, version_tag, version_id)
        VALUES (?, ?, ?, 'synthesis', ?, ?, '', ?, NULL, ?)
        """,
        (
            proposal_id,
            review_node.project_id,
            body.review_id,
            f"Proposal — {now}",
            json.dumps(meta),
            now,
            review_node.version_id,
        ),
    )
    await db.commit()

    _proposal_status[proposal_id] = {
        "status": "queued",
        "progress_message": "Proposal queued.",
    }

    background_tasks.add_task(_run_proposal_stub, proposal_id)

    return ProposalCreateResponse(proposal_id=proposal_id, status="queued", error=None)


@router.get("/{proposal_id}/status", response_model=ProposalStatusResponse)
async def get_proposal_status(
    proposal_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> ProposalStatusResponse:
    node = await repo.get_node(db, proposal_id)
    if node is None:
        raise HTTPException(
            status_code=404, detail=f"Proposal '{proposal_id}' not found."
        )

    state = _proposal_status.get(proposal_id, {})
    status = state.get("status", "complete")
    progress = state.get("progress_message")

    return ProposalStatusResponse(
        proposal_id=proposal_id,
        status=status,
        progress_message=progress,
        error=None,
    )
