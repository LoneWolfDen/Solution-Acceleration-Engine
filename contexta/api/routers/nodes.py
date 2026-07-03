"""GET /api/nodes/{node_id} — return the full ReviewPayload for a completed review node."""

from __future__ import annotations

import json

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_db
from ..schemas import (
    CitationOut,
    FindingOut,
    NodeDetailResponse,
    ReviewSummaryDetail,
)

router = APIRouter(tags=["nodes"])


def _count_by_routing(findings: list[dict], routing_value: str) -> int:
    return sum(1 for f in findings if f.get("mitigation_routing") == routing_value)


@router.get("/nodes/{node_id}", response_model=NodeDetailResponse)
async def get_node(
    node_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> NodeDetailResponse:
    """Return full review payload for a node, shaped for the UI detail pane.

    Looks up the review record whose node_id matches, then parses the
    content_markdown (ReviewNodePayload JSON) from the nodes table.
    """
    # Resolve node → review metadata.
    cursor = await db.execute(
        """
        SELECT r.id AS review_id, r.version_id, r.status, r.run_date, r.persona_roles
        FROM reviews r
        WHERE r.node_id = ?
        """,
        (node_id,),
    )
    review_row = await cursor.fetchone()

    # Also try direct node lookup (node may not have a review record yet).
    cursor2 = await db.execute(
        "SELECT id, project_id, version_id, content_markdown, created_at FROM nodes WHERE id = ?",
        (node_id,),
    )
    node_row = await cursor2.fetchone()

    if node_row is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")

    content_raw = node_row["content_markdown"] or "{}"
    try:
        payload = json.loads(content_raw)
    except json.JSONDecodeError:
        payload = {}

    # Build findings list.
    findings_raw: list[dict] = payload.get("findings", [])
    findings: list[FindingOut] = []
    for i, f in enumerate(findings_raw):
        citations = f.get("citations", [])
        first_citation: CitationOut | None = None
        if citations:
            c = citations[0]
            first_citation = CitationOut(
                file_path=c.get("file_path", ""),
                line_start=c.get("line_start", 1),
                line_end=c.get("line_end", 1),
                citation_type=c.get("citation_type", ""),
                excerpt=c.get("excerpt", ""),
            )
        findings.append(
            FindingOut(
                finding_id=str(i),
                type=f.get("dimension", "Unknown"),
                severity=f.get("confidence", "AMBER"),
                text=f.get("summary", ""),
                source_artifact=first_citation.file_path if first_citation else "",
                citation=first_citation,
            )
        )

    summary = ReviewSummaryDetail(
        risks=_count_by_routing(findings_raw, "Risk Register"),
        constraints=_count_by_routing(findings_raw, "Scope Modification"),
        dependencies=_count_by_routing(findings_raw, "Assumptions Matrix"),
        assumptions=_count_by_routing(findings_raw, "Both R&A"),
        action_items=_count_by_routing(findings_raw, "Ignored"),
    )

    review_id = review_row["review_id"] if review_row else node_id
    version_id = (
        review_row["version_id"]
        if review_row
        else node_row["version_id"]
    )
    status = review_row["status"] if review_row else "complete"
    run_date = review_row["run_date"] if review_row else node_row["created_at"]
    persona = review_row["persona_roles"] if review_row else "[]"

    return NodeDetailResponse(
        review_id=review_id,
        project_id=node_row["project_id"],
        version_id=version_id,
        status=status,
        run_date=run_date,
        persona=persona,
        findings=findings,
        summary=summary,
        error=None,
    )
