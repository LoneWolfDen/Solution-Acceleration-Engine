"""Schema v5 → v6: add review_links and proposal_review_links junction tables.

Revision ID: a1b2c3d4e5f6
Revises: 5d3059d1eb3f
Create Date: 2026-07-11

Changes
-------
Gap 1 (Review Linking):
  - CREATE TABLE review_links
      M:N junction between review_jobs.id (review_job_id) and review_jobs.id
      (linked_review_id).  Composite PK.  Self-link prevented by CHECK
      constraint.  Enables Prior Review Intelligence injection into LLM
      prompts.

Gap 2 (Proposal Re-Architecture):
  - CREATE TABLE proposal_review_links
      M:N junction between proposal_jobs.id (proposal_job_id) and
      review_jobs.id (review_job_id).  Composite PK.  Replaces the single
      proposal_jobs.review_job_id column as the canonical linkage mechanism
      while leaving the legacy column in place for backward compatibility.

Data migration (upgrade only):
  - Copies any existing proposal_jobs.review_job_id values into
    proposal_review_links so historical proposals are queryable through the
    new junction table without losing data.

NOTE: This project uses aiosqlite + a custom run_migrations() function in
contexta/db/schema.py as the authoritative migration runner at runtime.  This
Alembic revision file serves as a human-readable audit trail and a
developer-runnable offline migration for environments that prefer Alembic CLI
(e.g. CI schema checks, staging resets).  Both paths produce identical
end-state schemas.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "5d3059d1eb3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply v5 → v6 schema changes."""

    # ── review_links ─────────────────────────────────────────────────────────
    # M:N junction: which prior completed reviews provide context for a new
    # review run (Gap 1 — Prior Review Intelligence).
    op.create_table(
        "review_links",
        sa.Column(
            "review_job_id",
            sa.Text(),
            sa.ForeignKey("review_jobs.id"),
            nullable=False,
        ),
        sa.Column(
            "linked_review_id",
            sa.Text(),
            sa.ForeignKey("review_jobs.id"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("review_job_id", "linked_review_id"),
        sa.CheckConstraint(
            "review_job_id != linked_review_id",
            name="ck_review_links_no_self_link",
        ),
    )

    # ── proposal_review_links ─────────────────────────────────────────────────
    # M:N junction: which completed review jobs feed a given proposal synthesis
    # run (Gap 2 — Multi-Review Proposal Re-Architecture).
    op.create_table(
        "proposal_review_links",
        sa.Column(
            "proposal_job_id",
            sa.Text(),
            sa.ForeignKey("proposal_jobs.id"),
            nullable=False,
        ),
        sa.Column(
            "review_job_id",
            sa.Text(),
            sa.ForeignKey("review_jobs.id"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("proposal_job_id", "review_job_id"),
    )

    # ── Historical data migration ─────────────────────────────────────────────
    # Backfill proposal_review_links from the legacy single-FK column so that
    # any existing proposals are immediately queryable through the new table.
    op.execute(
        """
        INSERT OR IGNORE INTO proposal_review_links (proposal_job_id, review_job_id)
        SELECT id, review_job_id
        FROM proposal_jobs
        WHERE review_job_id IS NOT NULL
        """
    )


def downgrade() -> None:
    """Revert v6 → v5 schema changes.

    Drops both junction tables.  Historical data backfilled during upgrade is
    NOT restored to proposal_jobs.review_job_id because that column was never
    removed — the original 1:1 linkage is still intact after downgrade.
    """
    op.drop_table("proposal_review_links")
    op.drop_table("review_links")
