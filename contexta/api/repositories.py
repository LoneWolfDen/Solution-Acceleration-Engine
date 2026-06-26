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
    created_at: str = ""
    updated_at: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _row_to_artifact(row: aiosqlite.Row) -> ArtifactRow:
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
    return ProposalJobRow(
        id=row["id"],
        review_job_id=row["review_job_id"],
        status=row["status"],
        progress_message=row["progress_message"],
        node_id=row["node_id"],
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
    await conn.execute(
        """
        INSERT INTO artifacts
            (id, project_id, title, content, source, source_url, filename,
             tags, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (row_id, project_id, title, content, source, source_url, filename,
         json.dumps(tags), now),
    )
    await conn.commit()
    return ArtifactRow(
        id=row_id, project_id=project_id, title=title, content=content,
        source=source, source_url=source_url, filename=filename,
        tags=tags, is_active=True, created_at=now,
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
