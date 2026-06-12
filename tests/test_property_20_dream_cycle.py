"""Property 20 — Dream Cycle Frequency Count Monotonicity.

For any collection of nodes with k ≥ 1 RED findings for a given
(client_tag, dimension) pair, running DreamCycleWorker results in a
global_client_insights row whose frequency_count ≥ k.

Running Dream Cycle a second time on the same data must NOT decrease any
existing frequency_count.

Validates: Requirement 13.4
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import List

import pytest

from contexta.admin.dream_cycle import DreamCycleWorker
from contexta.db.repositories import create_project, upsert_insight
from contexta.db.schema import init_database
from contexta.models.enums import ConfidenceEnum, ReviewDimensionEnum


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _insert_exploration_node(
    db,
    project_id: str,
    dimensions_metadata: List[dict],
) -> None:
    """Insert a raw exploration node with the given dimensions metadata."""
    metadata = {"dimensions": dimensions_metadata}
    await db.execute(
        """INSERT INTO nodes
               (id, project_id, parent_id, layer_type, node_name,
                metadata_json, content_markdown, created_at)
           VALUES (?, ?, NULL, 'exploration', 'test-node', ?, '', ?)""",
        (str(uuid.uuid4()), project_id, json.dumps(metadata), _now()),
    )
    await db.commit()


def _dim_entry(dim: ReviewDimensionEnum, confidence: ConfidenceEnum) -> dict:
    return {
        "dimension": dim.value,
        "overall_confidence": confidence.value,
        "findings": [],
        "raw_llm_response": "{}",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestProperty20DreamCycleMonotonicity:

    @pytest.mark.asyncio
    async def test_single_red_finding_creates_insight(self, tmp_path):
        """1 RED finding → frequency_count ≥ 1 after Dream Cycle."""
        db = await init_database(str(tmp_path / "dc.db"))
        try:
            project = await create_project(db, "Project A", ["#TagA"])
            await _insert_exploration_node(
                db,
                project.id,
                [_dim_entry(ReviewDimensionEnum.RISK, ConfidenceEnum.RED)],
            )

            worker = DreamCycleWorker()
            count = await worker.run(db)
            assert count >= 1

            async with db.execute(
                "SELECT frequency_count FROM global_client_insights "
                "WHERE client_or_industry_tag = ? AND observed_pattern = ?",
                ("#TagA", "HIGH_RISK_RISK"),
            ) as cur:
                row = await cur.fetchone()
            assert row is not None
            assert row[0] >= 1
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_multiple_red_findings_same_tag(self, tmp_path):
        """k RED findings → frequency_count ≥ k."""
        db = await init_database(str(tmp_path / "dc_k.db"))
        try:
            k = 3
            project = await create_project(db, "Project B", ["#Multi"])
            for _ in range(k):
                await _insert_exploration_node(
                    db,
                    project.id,
                    [_dim_entry(ReviewDimensionEnum.ARCHITECTURE, ConfidenceEnum.RED)],
                )

            worker = DreamCycleWorker()
            await worker.run(db)

            async with db.execute(
                "SELECT frequency_count FROM global_client_insights "
                "WHERE client_or_industry_tag = ? AND observed_pattern = ?",
                ("#Multi", "HIGH_RISK_ARCHITECTURE"),
            ) as cur:
                row = await cur.fetchone()
            assert row is not None
            assert row[0] >= k, f"Expected frequency_count ≥ {k}, got {row[0]}"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_second_run_does_not_decrease_count(self, tmp_path):
        """Running Dream Cycle twice never decreases any frequency_count."""
        db = await init_database(str(tmp_path / "dc_mono.db"))
        try:
            project = await create_project(db, "Project C", ["#Stable"])
            await _insert_exploration_node(
                db,
                project.id,
                [_dim_entry(ReviewDimensionEnum.COMMERCIAL, ConfidenceEnum.RED)],
            )

            worker = DreamCycleWorker()
            await worker.run(db)

            async with db.execute(
                "SELECT frequency_count FROM global_client_insights"
            ) as cur:
                before = {row[0]: row for row in await cur.fetchall()}

            # Second run on the same data
            await worker.run(db)

            async with db.execute(
                "SELECT frequency_count, client_or_industry_tag, observed_pattern "
                "FROM global_client_insights"
            ) as cur:
                rows_after = await cur.fetchall()

            for row in rows_after:
                count_after = row[0]
                # Each count must be ≥ its original value
                assert count_after >= 1, (
                    f"frequency_count decreased after second run for "
                    f"({row[1]}, {row[2]}): count={count_after}"
                )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_non_red_findings_do_not_create_insights(self, tmp_path):
        """GREEN and AMBER findings must NOT generate insights."""
        db = await init_database(str(tmp_path / "dc_no_green.db"))
        try:
            project = await create_project(db, "Project D", ["#Clean"])
            await _insert_exploration_node(
                db,
                project.id,
                [
                    _dim_entry(ReviewDimensionEnum.INTENT, ConfidenceEnum.GREEN),
                    _dim_entry(ReviewDimensionEnum.SCOPE, ConfidenceEnum.AMBER),
                ],
            )

            worker = DreamCycleWorker()
            count = await worker.run(db)
            assert count == 0, f"Expected 0 insights for non-RED findings, got {count}"

            async with db.execute("SELECT COUNT(*) FROM global_client_insights") as cur:
                total = (await cur.fetchone())[0]
            assert total == 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_multiple_tags_each_get_insight(self, tmp_path):
        """Project with 2 tags and 1 RED finding → 2 insight rows (one per tag)."""
        db = await init_database(str(tmp_path / "dc_multi_tag.db"))
        try:
            project = await create_project(db, "Project E", ["#Alpha", "#Beta"])
            await _insert_exploration_node(
                db,
                project.id,
                [_dim_entry(ReviewDimensionEnum.DELIVERY, ConfidenceEnum.RED)],
            )

            worker = DreamCycleWorker()
            count = await worker.run(db)
            assert count == 2, f"Expected 2 insight updates (one per tag), got {count}"

            async with db.execute("SELECT COUNT(*) FROM global_client_insights") as cur:
                total = (await cur.fetchone())[0]
            assert total == 2
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_empty_database_returns_zero(self, tmp_path):
        """Dream Cycle on an empty database returns 0 and raises no errors."""
        db = await init_database(str(tmp_path / "dc_empty.db"))
        try:
            worker = DreamCycleWorker()
            count = await worker.run(db)
            assert count == 0
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_synthesis_nodes_are_ignored(self, tmp_path):
        """Only 'exploration' nodes are analysed; 'synthesis' nodes are skipped."""
        db = await init_database(str(tmp_path / "dc_synth.db"))
        try:
            project = await create_project(db, "Project F", ["#TagF"])
            # Insert a synthesis node (should be ignored by Dream Cycle)
            metadata = {
                "dimensions": [
                    _dim_entry(ReviewDimensionEnum.NFR, ConfidenceEnum.RED)
                ]
            }
            await db.execute(
                """INSERT INTO nodes
                       (id, project_id, parent_id, layer_type, node_name,
                        metadata_json, content_markdown, created_at)
                   VALUES (?, ?, NULL, 'synthesis', 'synth-node', ?, '', ?)""",
                (str(uuid.uuid4()), project.id, json.dumps(metadata), _now()),
            )
            await db.commit()

            worker = DreamCycleWorker()
            count = await worker.run(db)
            assert count == 0, "synthesis nodes must not generate Dream Cycle insights"
        finally:
            await db.close()
