"""
contexta/api/repositories.py — DB operations for the five web-API tables.

Covers: artifacts, artifact_version_links, review_jobs, proposal_jobs,
app_config.  Follows the same aiosqlite patterns as contexta/db/repositories.py.
All raw SQL lives here; no SQL appears in route handlers.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Row dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ArtifactRow:
    id: str
    project_id: str
    title: str
    content: str
    source: str                    # "upload" | "paste" | "url"
    source_url: Optional[str]
    filename: Optional[str]
    tags: List[str] = field(default_factory=list)
    is_active: bool = True
    created_at: str = ""
    line_count: int = 0
    content_preview: str = ""


@dataclass
class ReviewJobRow:
    id: str
    version_id: str
    persona_roles: List[str] = field(default_factory=list)
    context: str = ""
    status: str = "queued"         # "queued" | "running" | "complete" | "failed"
    progress_message: Optional[str] = None
    node_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ProposalJobRow:
    id: str
    review_job_id: str
    status: str = "queued"
    progress_message: Optional[str] = None
    node_id: Optional[str] = None
    metadata_json: str = "{}"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ReviewLinkRow:
    """One row in the review_links junction table (Gap 1)."""
    review_job_id: str
    linked_review_id: str


@dataclass
class ProposalReviewLinkRow:
    """One row in the proposal_review_links junction table (Gap 2)."""
    proposal_job_id: str
    review_job_id: str


@dataclass
class LinkableReviewItem:
    """A completed review job eligible to be linked as prior context."""
    review_id: str
    persona: str
    run_date: str


@dataclass
class ProposalListItem:
    """Summary row returned by list_proposals_for_version / list_proposals_for_project."""
    proposal_id: str
    status: str
    created_at: str
    progress_message: Optional[str]
    linked_review_count: int
    version_id: str = ""


@dataclass
class ReviewArtifactSnapshotItem:
    """One row returned by get_review_job_artifact_snapshot."""
    artifact_id: str
    title: str
    tags: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _row_to_artifact(row: aiosqlite.Row) -> ArtifactRow:
    # line_count/content_preview may be absent on rows fetched via SELECT *
    # before migration has run in a given process — guard with try/except so
    # older in-flight connections don't hard-fail.
    try:
        line_count = row["line_count"]
    except (IndexError, KeyError):
        line_count = 0
    try:
        content_preview = row["content_preview"]
    except (IndexError, KeyError):
        content_preview = ""
    return ArtifactRow(
        id=row["id"],
        project_id=row["project_id"],
        title=row["title"],
        content=row["content"] or "",
        source=row["source"],
        source_url=row["source_url"],
        filename=row["filename"],
        tags=json.loads(row["tags"] or "[]"),
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
        line_count=line_count or 0,
        content_preview=content_preview or "",
    )



def _row_to_review_job(row: aiosqlite.Row) -> ReviewJobRow:
    return ReviewJobRow(
        id=row["id"],
        version_id=row["version_id"],
        persona_roles=json.loads(row["persona_roles"] or "[]"),
        context=row["context"] or "",
        status=row["status"],
        progress_message=row["progress_message"],
        node_id=row["node_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_proposal_job(row: aiosqlite.Row) -> ProposalJobRow:
    try:
        metadata_json = row["metadata_json"] or "{}"
    except (IndexError, KeyError):
        metadata_json = "{}"
    return ProposalJobRow(
        id=row["id"],
        review_job_id=row["review_job_id"],
        status=row["status"],
        progress_message=row["progress_message"],
        node_id=row["node_id"],
        metadata_json=metadata_json,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Artifacts
# ─────────────────────────────────────────────────────────────────────────────

async def create_artifact(
    conn: aiosqlite.Connection,
    project_id: str,
    title: str,
    content: str,
    source: str,
    tags: List[str],
    source_url: Optional[str] = None,
    filename: Optional[str] = None,
) -> ArtifactRow:
    row_id = _new_id()
    now = _now_iso()
    line_count = len(content.splitlines())
    content_preview = content[:280]
    await conn.execute(
        """
        INSERT INTO artifacts
            (id, project_id, title, content, source, source_url, filename,
             tags, is_active, created_at, line_count, content_preview)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (row_id, project_id, title, content, source, source_url, filename,
         json.dumps(tags), now, line_count, content_preview),
    )
    await conn.commit()
    return ArtifactRow(
        id=row_id, project_id=project_id, title=title, content=content,
        source=source, source_url=source_url, filename=filename,
        tags=tags, is_active=True, created_at=now,
        line_count=line_count, content_preview=content_preview,
    )


async def get_artifact(
    conn: aiosqlite.Connection, artifact_id: str
) -> Optional[ArtifactRow]:
    cursor = await conn.execute(
        "SELECT * FROM artifacts WHERE id = ?", (artifact_id,)
    )
    row = await cursor.fetchone()
    return _row_to_artifact(row) if row else None


async def list_artifacts_for_project(
    conn: aiosqlite.Connection, project_id: str
) -> List[ArtifactRow]:
    cursor = await conn.execute(
        "SELECT * FROM artifacts WHERE project_id = ? ORDER BY created_at",
        (project_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_artifact(r) for r in rows]


async def update_artifact_active(
    conn: aiosqlite.Connection, artifact_id: str, is_active: bool
) -> Optional[ArtifactRow]:
    await conn.execute(
        "UPDATE artifacts SET is_active = ? WHERE id = ?",
        (1 if is_active else 0, artifact_id),
    )
    await conn.commit()
    return await get_artifact(conn, artifact_id)


async def delete_artifact(
    conn: aiosqlite.Connection, artifact_id: str
) -> bool:
    cursor = await conn.execute(
        "SELECT id FROM artifacts WHERE id = ?", (artifact_id,)
    )
    if not await cursor.fetchone():
        return False
    await conn.execute(
        "DELETE FROM artifact_version_links WHERE artifact_id = ?", (artifact_id,)
    )
    await conn.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
    await conn.commit()
    return True



# ─────────────────────────────────────────────────────────────────────────────
# Artifact-Version Links
# ─────────────────────────────────────────────────────────────────────────────

async def link_artifacts_to_version(
    conn: aiosqlite.Connection, version_id: str, artifact_ids: List[str]
) -> None:
    for aid in artifact_ids:
        await conn.execute(
            "INSERT OR IGNORE INTO artifact_version_links (artifact_id, version_id) VALUES (?, ?)",
            (aid, version_id),
        )
    await conn.commit()


async def list_artifacts_for_version(
    conn: aiosqlite.Connection, version_id: str
) -> List[ArtifactRow]:
    cursor = await conn.execute(
        """
        SELECT a.* FROM artifacts a
        JOIN artifact_version_links avl ON a.id = avl.artifact_id
        WHERE avl.version_id = ?
        ORDER BY a.created_at
        """,
        (version_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_artifact(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Review Jobs
# ─────────────────────────────────────────────────────────────────────────────

async def create_review_job(
    conn: aiosqlite.Connection,
    version_id: str,
    persona_roles: List[str],
    context: str,
) -> ReviewJobRow:
    row_id = _new_id()
    now = _now_iso()
    await conn.execute(
        """
        INSERT INTO review_jobs
            (id, version_id, persona_roles, context, status,
             progress_message, node_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'queued', NULL, NULL, ?, ?)
        """,
        (row_id, version_id, json.dumps(persona_roles), context, now, now),
    )
    await conn.commit()
    return ReviewJobRow(
        id=row_id, version_id=version_id, persona_roles=persona_roles,
        context=context, status="queued", created_at=now, updated_at=now,
    )


async def get_review_job(
    conn: aiosqlite.Connection, job_id: str
) -> Optional[ReviewJobRow]:
    cursor = await conn.execute(
        "SELECT * FROM review_jobs WHERE id = ?", (job_id,)
    )
    row = await cursor.fetchone()
    return _row_to_review_job(row) if row else None


async def list_review_jobs_for_version(
    conn: aiosqlite.Connection, version_id: str
) -> List[ReviewJobRow]:
    cursor = await conn.execute(
        "SELECT * FROM review_jobs WHERE version_id = ? ORDER BY created_at",
        (version_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_review_job(r) for r in rows]


async def update_review_job_status(
    conn: aiosqlite.Connection,
    job_id: str,
    status: str,
    progress_message: Optional[str] = None,
    node_id: Optional[str] = None,
) -> Optional[ReviewJobRow]:
    now = _now_iso()
    await conn.execute(
        """
        UPDATE review_jobs
        SET status = ?, progress_message = ?,
            node_id = COALESCE(?, node_id), updated_at = ?
        WHERE id = ?
        """,
        (status, progress_message, node_id, now, job_id),
    )
    await conn.commit()
    return await get_review_job(conn, job_id)



# ─────────────────────────────────────────────────────────────────────────────
# Proposal Jobs
# ─────────────────────────────────────────────────────────────────────────────

async def create_proposal_job(
    conn: aiosqlite.Connection, review_job_id: str
) -> ProposalJobRow:
    row_id = _new_id()
    now = _now_iso()
    await conn.execute(
        """
        INSERT INTO proposal_jobs
            (id, review_job_id, status, progress_message, node_id, created_at, updated_at)
        VALUES (?, ?, 'queued', NULL, NULL, ?, ?)
        """,
        (row_id, review_job_id, now, now),
    )
    await conn.commit()
    return ProposalJobRow(
        id=row_id, review_job_id=review_job_id, status="queued",
        created_at=now, updated_at=now,
    )


async def get_proposal_job(
    conn: aiosqlite.Connection, job_id: str
) -> Optional[ProposalJobRow]:
    cursor = await conn.execute(
        "SELECT * FROM proposal_jobs WHERE id = ?", (job_id,)
    )
    row = await cursor.fetchone()
    return _row_to_proposal_job(row) if row else None


async def update_proposal_job_status(
    conn: aiosqlite.Connection,
    job_id: str,
    status: str,
    progress_message: Optional[str] = None,
    node_id: Optional[str] = None,
) -> Optional[ProposalJobRow]:
    now = _now_iso()
    await conn.execute(
        """
        UPDATE proposal_jobs
        SET status = ?, progress_message = ?,
            node_id = COALESCE(?, node_id), updated_at = ?
        WHERE id = ?
        """,
        (status, progress_message, node_id, now, job_id),
    )
    await conn.commit()
    return await get_proposal_job(conn, job_id)


# ─────────────────────────────────────────────────────────────────────────────
# App Config
# ─────────────────────────────────────────────────────────────────────────────

async def get_config_value(
    conn: aiosqlite.Connection, key: str
) -> Optional[str]:
    cursor = await conn.execute(
        "SELECT value FROM app_config WHERE key = ?", (key,)
    )
    row = await cursor.fetchone()
    return row["value"] if row else None


async def set_config_value(
    conn: aiosqlite.Connection, key: str, value: str
) -> None:
    await conn.execute(
        "INSERT INTO app_config (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await conn.commit()


async def get_all_config(conn: aiosqlite.Connection) -> Dict[str, str]:
    cursor = await conn.execute("SELECT key, value FROM app_config")
    rows = await cursor.fetchall()
    return {r["key"]: r["value"] for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# Project cascade delete
# ─────────────────────────────────────────────────────────────────────────────

async def delete_project_cascade(
    conn: aiosqlite.Connection, project_id: str
) -> bool:
    """Delete a project and all child data.  Returns False if not found."""
    cursor = await conn.execute(
        "SELECT id FROM projects WHERE id = ?", (project_id,)
    )
    if not await cursor.fetchone():
        return False

    # Delete child tables in dependency order (deepest first)
    await conn.execute(
        """
        DELETE FROM proposal_jobs WHERE review_job_id IN (
            SELECT id FROM review_jobs WHERE version_id IN (
                SELECT id FROM versions WHERE project_id = ?
            )
        )
        """,
        (project_id,),
    )
    await conn.execute(
        "DELETE FROM review_jobs WHERE version_id IN "
        "(SELECT id FROM versions WHERE project_id = ?)",
        (project_id,),
    )
    await conn.execute(
        "DELETE FROM artifact_version_links WHERE version_id IN "
        "(SELECT id FROM versions WHERE project_id = ?)",
        (project_id,),
    )
    await conn.execute(
        "DELETE FROM artifacts WHERE project_id = ?", (project_id,)
    )
    await conn.execute(
        "DELETE FROM nodes WHERE project_id = ?", (project_id,)
    )
    await conn.execute(
        "DELETE FROM intelligence_layer WHERE project_id = ?", (project_id,)
    )
    await conn.execute(
        "DELETE FROM versions WHERE project_id = ?", (project_id,)
    )
    await conn.execute(
        "DELETE FROM projects WHERE id = ?", (project_id,)
    )
    await conn.commit()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Project stats
# ─────────────────────────────────────────────────────────────────────────────

async def get_project_stats(
    conn: aiosqlite.Connection, project_id: str
) -> Dict[str, int]:
    """Return version_count, review_count, storage_bytes for one project."""
    cur = await conn.execute(
        "SELECT COUNT(*) FROM versions WHERE project_id = ?", (project_id,)
    )
    version_count: int = (await cur.fetchone())[0]

    cur = await conn.execute(
        "SELECT COUNT(*) FROM review_jobs "
        "WHERE version_id IN (SELECT id FROM versions WHERE project_id = ?)",
        (project_id,),
    )
    review_count: int = (await cur.fetchone())[0]

    cur = await conn.execute(
        "SELECT COALESCE(SUM(LENGTH(content_markdown)), 0) "
        "FROM nodes WHERE project_id = ?",
        (project_id,),
    )
    node_bytes: int = (await cur.fetchone())[0]

    cur = await conn.execute(
        "SELECT COALESCE(SUM(LENGTH(content)), 0) "
        "FROM artifacts WHERE project_id = ?",
        (project_id,),
    )
    artifact_bytes: int = (await cur.fetchone())[0]

    return {
        "version_count": version_count,
        "review_count": review_count,
        "storage_bytes": node_bytes + artifact_bytes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Review Links  (Gap 1 — v6 junction table)
# ─────────────────────────────────────────────────────────────────────────────

async def insert_review_links(
    conn: aiosqlite.Connection,
    review_job_id: str,
    linked_ids: List[str],
) -> None:
    """Bulk-insert rows into ``review_links`` for a newly created review job.

    Each ID in *linked_ids* becomes one (review_job_id, linked_review_id) row.
    ``INSERT OR IGNORE`` is used so callers can safely retry without creating
    duplicate rows.

    Args:
        conn:           Open aiosqlite connection.
        review_job_id:  The new Review_Job whose context links are being stored.
        linked_ids:     IDs of prior completed Review_Jobs to link as context.
    """
    if not linked_ids:
        return
    for linked_id in linked_ids:
        await conn.execute(
            "INSERT OR IGNORE INTO review_links (review_job_id, linked_review_id) VALUES (?, ?)",
            (review_job_id, linked_id),
        )
    await conn.commit()


async def get_linked_review_ids(
    conn: aiosqlite.Connection,
    review_job_id: str,
) -> List[str]:
    """Return all linked_review_id values for a given review job.

    Args:
        conn:           Open aiosqlite connection.
        review_job_id:  FK → review_jobs.id whose links to retrieve.

    Returns:
        List of linked review job IDs.  Empty list if none are linked.
    """
    cursor = await conn.execute(
        "SELECT linked_review_id FROM review_links WHERE review_job_id = ?",
        (review_job_id,),
    )
    rows = await cursor.fetchall()
    return [row["linked_review_id"] for row in rows]


async def list_linkable_reviews(
    conn: aiosqlite.Connection,
    version_id: str,
) -> List[LinkableReviewItem]:
    """Return all completed Review_Jobs for *version_id* eligible for linking.

    Only jobs with ``status = 'complete'`` are returned — in-flight or failed
    jobs cannot contribute Prior Review Intelligence.

    Args:
        conn:       Open aiosqlite connection.
        version_id: FK → versions.id to filter on.

    Returns:
        List of :class:`LinkableReviewItem` ordered by creation date.
    """
    cursor = await conn.execute(
        """
        SELECT id, persona_roles, created_at
        FROM review_jobs
        WHERE version_id = ? AND status = 'complete'
        ORDER BY created_at
        """,
        (version_id,),
    )
    rows = await cursor.fetchall()
    items: List[LinkableReviewItem] = []
    for row in rows:
        # Extract first persona role as the display label; fall back to "unknown".
        roles = json.loads(row["persona_roles"] or "[]")
        persona = roles[0] if roles else "unknown"
        items.append(
            LinkableReviewItem(
                review_id=row["id"],
                persona=persona,
                run_date=row["created_at"],
            )
        )
    return items


# ─────────────────────────────────────────────────────────────────────────────
# Proposal Review Links  (Gap 2 — v6 junction table)
# ─────────────────────────────────────────────────────────────────────────────

async def insert_proposal_review_links(
    conn: aiosqlite.Connection,
    proposal_job_id: str,
    review_ids: List[str],
) -> None:
    """Bulk-insert rows into ``proposal_review_links`` for a new proposal job.

    Each ID in *review_ids* becomes one (proposal_job_id, review_job_id) row.
    ``INSERT OR IGNORE`` ensures idempotency.

    Args:
        conn:             Open aiosqlite connection.
        proposal_job_id:  FK → proposal_jobs.id of the new proposal.
        review_ids:       IDs of completed Review_Jobs feeding this proposal.
    """
    if not review_ids:
        return
    for review_id in review_ids:
        await conn.execute(
            "INSERT OR IGNORE INTO proposal_review_links (proposal_job_id, review_job_id) VALUES (?, ?)",
            (proposal_job_id, review_id),
        )
    await conn.commit()


async def get_linked_proposal_review_ids(
    conn: aiosqlite.Connection,
    proposal_job_id: str,
) -> List[str]:
    """Return all review_job_id values linked to a given proposal job.

    Used by the pipeline bridge to load all exploration nodes for a
    multi-review proposal (Gap 2).

    Args:
        conn:             Open aiosqlite connection.
        proposal_job_id:  FK → proposal_jobs.id.

    Returns:
        List of review job IDs.  Empty list if no rows exist (legacy proposals
        with only the FK column should fall back to proposal_jobs.review_job_id).
    """
    cursor = await conn.execute(
        "SELECT review_job_id FROM proposal_review_links WHERE proposal_job_id = ?",
        (proposal_job_id,),
    )
    rows = await cursor.fetchall()
    return [row["review_job_id"] for row in rows]


async def list_proposals_for_version(
    conn: aiosqlite.Connection,
    version_id: str,
) -> List[ProposalListItem]:
    """Return all Proposal_Jobs whose linked reviews belong to *version_id*.

    Joins ``proposal_review_links`` → ``review_jobs`` to filter by version,
    then groups to deduplicate proposals that link multiple reviews and to
    count the number of linked reviews per proposal.

    Args:
        conn:       Open aiosqlite connection.
        version_id: FK → versions.id to filter on.

    Returns:
        List of :class:`ProposalListItem` ordered by proposal creation date.
        Empty list if no proposals exist for this version.
    """
    cursor = await conn.execute(
        """
        SELECT
            pj.id               AS proposal_id,
            pj.status           AS status,
            pj.created_at       AS created_at,
            pj.progress_message AS progress_message,
            COUNT(prl.review_job_id) AS linked_review_count,
            MIN(rj.version_id) AS version_id
        FROM proposal_jobs pj
        JOIN proposal_review_links prl ON prl.proposal_job_id = pj.id
        JOIN review_jobs rj ON rj.id = prl.review_job_id
        WHERE rj.version_id = ?
        GROUP BY pj.id
        ORDER BY pj.created_at
        """,
        (version_id,),
    )
    rows = await cursor.fetchall()
    return [
        ProposalListItem(
            proposal_id=row["proposal_id"],
            status=row["status"],
            created_at=row["created_at"],
            progress_message=row["progress_message"],
            linked_review_count=row["linked_review_count"],
            version_id=row["version_id"] or "",
        )
        for row in rows
    ]


async def list_proposals_for_project(
    conn: aiosqlite.Connection,
    project_id: str,
) -> List[ProposalListItem]:
    """Return all Proposal_Jobs whose linked reviews belong to any version
    under *project_id* (Requirement A1 — additive project-scope aggregation).

    This mirrors ``list_proposals_for_version`` but joins one level further
    through ``versions`` to scope by project instead of by a single version.
    It does NOT replace or weaken the existing version-scoped guard anywhere
    else — it is a separate, read-only aggregation query.

    Args:
        conn:       Open aiosqlite connection.
        project_id: FK → projects.id to filter on.

    Returns:
        List of :class:`ProposalListItem` (with `version_id` populated so the
        UI can group/label proposals by version) ordered by proposal creation
        date.  Empty list if the project has no proposals.
    """
    cursor = await conn.execute(
        """
        SELECT
            pj.id               AS proposal_id,
            pj.status           AS status,
            pj.created_at       AS created_at,
            pj.progress_message AS progress_message,
            COUNT(prl.review_job_id) AS linked_review_count,
            MIN(rj.version_id) AS version_id
        FROM proposal_jobs pj
        JOIN proposal_review_links prl ON prl.proposal_job_id = pj.id
        JOIN review_jobs rj ON rj.id = prl.review_job_id
        JOIN versions v ON v.id = rj.version_id
        WHERE v.project_id = ?
        GROUP BY pj.id
        ORDER BY pj.created_at
        """,
        (project_id,),
    )
    rows = await cursor.fetchall()
    return [
        ProposalListItem(
            proposal_id=row["proposal_id"],
            status=row["status"],
            created_at=row["created_at"],
            progress_message=row["progress_message"],
            linked_review_count=row["linked_review_count"],
            version_id=row["version_id"] or "",
        )
        for row in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Review Job Artifact Snapshots  (Requirement A2 — v7 junction table)
# ─────────────────────────────────────────────────────────────────────────────

async def insert_review_job_artifact_snapshot(
    conn: aiosqlite.Connection,
    review_job_id: str,
    artifact_ids: List[str],
) -> None:
    """Bulk-insert the artifact IDs active at review-creation time.

    Snapshotting NEVER blocks or fails review creation: an empty
    *artifact_ids* list is valid (zero active artifacts on the version) and
    simply results in no rows being written.

    Args:
        conn:          Open aiosqlite connection.
        review_job_id: FK → review_jobs.id — the review job being snapshotted.
        artifact_ids:  IDs of artifacts active on the version at this moment.
    """
    if not artifact_ids:
        return
    for artifact_id in artifact_ids:
        await conn.execute(
            "INSERT OR IGNORE INTO review_job_artifact_snapshots "
            "(review_job_id, artifact_id) VALUES (?, ?)",
            (review_job_id, artifact_id),
        )
    await conn.commit()


async def get_review_job_artifact_snapshot(
    conn: aiosqlite.Connection,
    review_job_id: str,
) -> List[ReviewArtifactSnapshotItem]:
    """Return the artifact set frozen at the time *review_job_id* was created.

    This is immutable provenance: later changes to `artifacts.is_active` (or
    even deleting the artifact-version link) do not alter what this function
    returns, since it reads only from the snapshot junction table.

    Args:
        conn:          Open aiosqlite connection.
        review_job_id: FK → review_jobs.id whose snapshot to retrieve.

    Returns:
        List of :class:`ReviewArtifactSnapshotItem`, ordered by artifact
        creation time.  Empty list if the review had zero active artifacts
        at creation time (not an error).
    """
    cursor = await conn.execute(
        """
        SELECT a.id AS artifact_id, a.title AS title, a.tags AS tags
        FROM review_job_artifact_snapshots rjas
        JOIN artifacts a ON a.id = rjas.artifact_id
        WHERE rjas.review_job_id = ?
        ORDER BY a.created_at
        """,
        (review_job_id,),
    )
    rows = await cursor.fetchall()
    return [
        ReviewArtifactSnapshotItem(
            artifact_id=row["artifact_id"],
            title=row["title"],
            tags=json.loads(row["tags"] or "[]"),
        )
        for row in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Node metadata patch  (Gap 5 — routing decisions; Gap 4 — advisor alerts)
# ─────────────────────────────────────────────────────────────────────────────

async def update_node_metadata(
    conn: aiosqlite.Connection,
    node_id: str,
    metadata_json: str,
) -> None:
    """Patch the ``metadata_json`` column on a node row in-place.

    Callers are responsible for reading the current metadata (via
    ``db_repo.get_node``), merging their changes into it, serialising to a
    JSON string, then calling this function to persist.

    Args:
        conn:          Open aiosqlite connection.
        node_id:       PK of the node row to update.
        metadata_json: Fully serialised JSON string to write into the column.

    Raises:
        ValueError: if *node_id* does not exist in the ``nodes`` table.
    """
    # Confirm the row exists before writing to avoid silent no-ops.
    cursor = await conn.execute(
        "SELECT id FROM nodes WHERE id = ?", (node_id,)
    )
    if await cursor.fetchone() is None:
        raise ValueError(f"Node '{node_id}' not found.")

    await conn.execute(
        "UPDATE nodes SET metadata_json = ? WHERE id = ?",
        (metadata_json, node_id),
    )
    await conn.commit()
