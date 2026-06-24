"""contexta/harness/seed_database.py — Database seeding utility.

Seeds a minimal blueprint and one exploration node into the SQLite database.
Intended for local development bootstrapping and CI fixture setup.

Usage::

    python -m contexta.harness.seed_database

The script is idempotent in the sense that it always creates *new* rows —
it does not check for duplicates.  Run against a fresh database or truncate
first if you need a clean state.
"""

from __future__ import annotations

import asyncio
import os

import aiosqlite

from ..db.repositories import (
    activate_blueprint,
    create_project,
    save_blueprint_version,
    write_node,
)
from ..models.citations import SourceCitation
from ..models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from ..models.findings import IssueFinding
from ..models.payloads import ReviewNodePayload

_DB_PATH: str = os.environ.get("CONTEXTA_DB_PATH", "./contexta.db")


# ── Seeding functions ─────────────────────────────────────────────────────────


async def seed_blueprint(
    conn: aiosqlite.Connection,
    name: str = "Alpha",
    version: str = "1.0.0",
    prompt_text: str = (
        "You are a senior technical delivery manager. "
        "Review the provided solution proposal with rigorous scrutiny. "
        "Focus on delivery risk and technical feasibility."
    ),
) -> str:
    """Insert a new blueprint row and activate it.

    Parameters
    ----------
    conn:
        Open aiosqlite connection.
    name:
        Human-readable blueprint name.
    version:
        Version string, e.g. ``"1.0.0"``.
    prompt_text:
        Master prompt text embedded in every dimension review.

    Returns
    -------
    str
        The ``id`` of the newly created and activated blueprint.
    """
    bp = await save_blueprint_version(
        conn,
        name=name,
        version=version,
        prompt_text=prompt_text,
    )
    await activate_blueprint(conn, bp.id)
    print(f"[seed] Blueprint created and activated: '{bp.blueprint_name}' v{bp.version_string} (id={bp.id})")
    return bp.id


async def seed_project_node(
    conn: aiosqlite.Connection,
    project_name: str = "Alpha-Project",
    node_name: str = "Test-Node-001",
) -> None:
    """Insert a test project with one exploration node.

    The node holds a minimal ``ReviewNodePayload`` for the ``INTENT``
    dimension with one ``IssueFinding`` per ``ReviewDimensionEnum`` value.
    All citation fields use the correct ``SourceCitation`` schema.

    Parameters
    ----------
    conn:
        Open aiosqlite connection.
    project_name:
        Name for the created project.
    node_name:
        Name for the created exploration node.
    """
    proj = await create_project(conn, project_name, ["gen-ai"])

    # One finding per dimension — each with valid SourceCitation fields.
    findings = [
        IssueFinding(
            dimension=dim,
            confidence=ConfidenceEnum.GREEN,
            summary=f"No issues detected in {dim.value}.",
            detail=f"Full analysis of {dim.value} dimension shows no critical gaps.",
            citations=[
                SourceCitation(
                    file_path="docs/sow.pdf",
                    line_start=1,
                    line_end=3,
                    citation_type=CitationTypeEnum.DIRECT_REFERENCE,
                    excerpt="Sample requirement text used for seeding.",
                )
            ],
            mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
        )
        for dim in ReviewDimensionEnum
    ]

    payload = ReviewNodePayload(
        dimension=ReviewDimensionEnum.INTENT,
        findings=findings,
        overall_confidence=ConfidenceEnum.GREEN,
        raw_llm_response="Seeded via harness — not a real LLM response.",
    )

    node = await write_node(
        conn,
        project_id=proj.id,
        parent_id=None,
        layer_type="exploration",
        node_name=node_name,
        payload=payload,
        metadata={"seeded_by": "contexta.harness.seed_database"},
    )
    print(
        f"[seed] Project '{proj.name}' created. "
        f"Node '{node.node_name}' written (id={node.id})."
    )


# ── Entry point ───────────────────────────────────────────────────────────────


async def main() -> None:
    """Seed blueprint + project node into the database at ``CONTEXTA_DB_PATH``."""
    print(f"[seed] Connecting to database: {_DB_PATH}")
    async with aiosqlite.connect(_DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await seed_blueprint(conn)
        await seed_project_node(conn)
    print("[seed] Done.")


if __name__ == "__main__":
    asyncio.run(main())
