"""
contexta/api/routers/nodes.py

Node-level operations not covered by the reviews router:

  POST /api/nodes/{node_id}/fork              — Gap 3: branch a node into a fork
  POST /api/nodes/{node_id}/routing-decision  — Gap 5: record scope routing choice
  GET  /api/nodes/{node_id}/export            — Gap 6: download node as JSONPacket

All three endpoints share the same 404 guard: load the node first, raise if
absent.  Raw SQL is kept out of this file — every DB operation is delegated
to the repository layer.
"""

from __future__ import annotations

import json
import logging

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from contexta.api import repositories as api_repo
from contexta.api import schemas
from contexta.api.dependencies import get_db
from contexta.db import repositories as db_repo
from contexta.models.export import EXPORT_SCHEMA_VERSION, JSONPacket

logger = logging.getLogger(__name__)
router = APIRouter(tags=["nodes"])

# Valid routing decision values (Gap 5 — Requirement 5.3).
_VALID_DECISIONS = frozenset(
    {"risk_register", "assumptions_matrix", "scope_modification"}
)


# ── Fork (Gap 3) ──────────────────────────────────────────────────────────────

@router.post(
    "/nodes/{node_id}/fork",
    response_model=schemas.ForkNodeResponse,
    status_code=201,
)
async def fork_node(
    node_id: str,
    body: schemas.ForkNodeRequest,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.ForkNodeResponse:
    """Branch an existing node into a new fork.

    Gap 3 — Requirements 3.1–3.4:
    - The new node inherits ``project_id``, ``version_id``, and ``layer_type``
      from the parent via ``db_repo.fork_node()`` (Wave 1 patch already
      implements the ``version_id`` fallback inheritance).
    - ``parent_id`` is set to the source ``node_id``.
    - Returns HTTP 201 with the new node's ID, name, and creation timestamp.
    - Returns HTTP 404 when the parent node does not exist.
    """
    if not body.name or not body.name.strip():
        raise HTTPException(
            status_code=422, detail="Fork name must not be empty."
        )

    try:
        forked = await db_repo.fork_node(
            conn,
            parent_node_id=node_id,
            new_node_name=body.name.strip(),
        )
    except ValueError as exc:
        # fork_node raises ValueError when the parent does not exist.
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    logger.info(
        "[INFO] Node '%s' forked → new node '%s' (%s)",
        node_id, forked.id, forked.node_name,
    )
    return schemas.ForkNodeResponse(
        node_id=forked.id,
        name=forked.node_name,
        created_at=forked.created_at,
    )


# ── Routing Decision (Gap 5) ──────────────────────────────────────────────────

@router.post(
    "/nodes/{node_id}/routing-decision",
    response_model=schemas.RoutingDecisionResponse,
)
async def record_routing_decision(
    node_id: str,
    body: schemas.RoutingDecisionRequest,
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.RoutingDecisionResponse:
    """Record a scope routing decision on a node's metadata.

    Gap 5 — Requirements 5.3–5.5:
    - ``decision`` must be one of ``risk_register``, ``assumptions_matrix``,
      or ``scope_modification``.
    - When ``decision == 'scope_modification'``, ``acknowledged`` must be
      ``True`` (HTTP 422 otherwise — Property 11).
    - The decision is appended to ``metadata_json["routing_decisions"]`` and
      persisted via ``api_repo.update_node_metadata()``.
    - Returns HTTP 404 when the node does not exist.
    """
    # Validate decision value.
    if body.decision not in _VALID_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"decision must be one of "
                f"{sorted(_VALID_DECISIONS)}; got '{body.decision}'."
            ),
        )

    # Scope modification requires explicit acknowledgement (Property 11).
    if body.decision == "scope_modification" and not body.acknowledged:
        raise HTTPException(
            status_code=422,
            detail=(
                "Scope modification decisions require explicit acknowledgement. "
                "Set acknowledged=true to confirm this scope change."
            ),
        )

    # Load node — 404 if absent.
    node = await db_repo.get_node(conn, node_id)
    if node is None:
        raise HTTPException(
            status_code=404, detail=f"Node '{node_id}' not found."
        )

    # Parse existing metadata and append the new decision.
    raw_meta = node.metadata_json
    metadata: dict = (
        json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta)
    )

    routing_decisions: list = metadata.get("routing_decisions") or []
    routing_decisions.append(
        {
            "finding_id": body.finding_id,
            "decision": body.decision,
            "acknowledged": bool(body.acknowledged),
        }
    )
    metadata["routing_decisions"] = routing_decisions

    # Persist via the repository helper (raises ValueError if node vanished).
    try:
        await api_repo.update_node_metadata(conn, node_id, json.dumps(metadata))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    logger.info(
        "[INFO] Routing decision '%s' recorded on node '%s' (finding=%s)",
        body.decision, node_id, body.finding_id,
    )
    return schemas.RoutingDecisionResponse(status="recorded")


# ── JSON Export (Gap 6) ───────────────────────────────────────────────────────

@router.get("/nodes/{node_id}/export")
async def export_node(
    node_id: str,
    conn: aiosqlite.Connection = Depends(get_db),
) -> StreamingResponse:
    """Serialise a node's full pipeline state as a downloadable JSONPacket.

    Gap 6 — Requirements 6.1–6.4:
    - Builds a ``JSONPacket`` from the node row, its parent project, and all
      12 dimension payloads stored in ``metadata_json["dimensions"]``.
    - Returns a ``StreamingResponse`` with:
        ``Content-Type: application/json``
        ``Content-Disposition: attachment; filename="{node_name}_{node_id}.json"``
    - Returns HTTP 404 when the node does not exist.
    - ``schema_version`` is always set to ``EXPORT_SCHEMA_VERSION`` (Req 6.2).
    """
    from contexta.models.payloads import ReviewNodePayload

    # Load node — 404 if absent.
    node = await db_repo.get_node(conn, node_id)
    if node is None:
        raise HTTPException(
            status_code=404, detail=f"Node '{node_id}' not found."
        )

    # Load parent project for name and global_tags.
    project = await db_repo.get_project(conn, node.project_id)
    project_name = project.name if project else ""
    global_tags = project.global_tags if project else []

    # Parse metadata.
    raw_meta = node.metadata_json
    metadata: dict = (
        json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta or {})
    )

    # Reconstruct ReviewNodePayload list from dimensions stored in metadata.
    payloads: list[ReviewNodePayload] = []
    dimension_dicts = metadata.get("dimensions") or []
    for d in dimension_dicts:
        try:
            payloads.append(ReviewNodePayload.model_validate(d))
        except Exception:
            logger.warning(
                "export_node: could not parse dimension payload for node %s", node_id
            )

    # Fall back to content_markdown for pre-Milestone-4 nodes.
    if not payloads and node.content_markdown:
        try:
            payloads.append(ReviewNodePayload.model_validate_json(node.content_markdown))
        except Exception:
            logger.warning(
                "export_node: could not parse content_markdown for node %s", node_id
            )

    # Extract arbitrator result if present.
    arbitrator_result = None
    raw_arb = metadata.get("arbitrator_result")
    if raw_arb:
        try:
            from contexta.models.export import ExportArbitratorResult
            arbitrator_result = ExportArbitratorResult.model_validate(raw_arb)
        except Exception:
            logger.warning(
                "export_node: could not parse arbitrator_result for node %s", node_id
            )

    # Build the clean metadata dict (strip internal keys already surfaced
    # as dedicated JSONPacket fields so the ``metadata`` bag stays minimal).
    export_metadata = {
        k: v
        for k, v in metadata.items()
        if k not in {"dimensions", "routing_decisions", "arbitrator_result"}
    }

    packet = JSONPacket(
        schema_version=EXPORT_SCHEMA_VERSION,
        project_id=node.project_id,
        project_name=project_name,
        global_tags=global_tags,
        node_id=node.id,
        node_name=node.node_name,
        parent_node_id=node.parent_id,
        layer_type=node.layer_type,
        created_at=node.created_at,
        payloads=payloads,
        arbitrator_result=arbitrator_result,
        routing_decisions=metadata.get("routing_decisions") or [],
        metadata=export_metadata,
        version_tag=node.version_tag,
    )

    # Sanitise node_name for use as a filename (replace spaces / slashes).
    safe_name = node.node_name.replace(" ", "_").replace("/", "-")[:80]
    filename = f"{safe_name}_{node_id}.json"

    return StreamingResponse(
        content=iter([packet.model_dump_json(indent=2)]),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
