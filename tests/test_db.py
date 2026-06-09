"""
tests/test_db.py — Property and integration tests for the SQLite DAL.

Properties covered:
  Property 6:  DB Node Write Validation Guard
               write_node() with a post-construction mutated payload raises
               ValidationError and inserts no row.
  Property 21: One-Active Blueprint Invariant
               After activate_blueprint(id), exactly one row has is_active=1
               and its id matches the argument — regardless of prior state.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from contexta.db.models import BlueprintRow, NodeRow, ProjectRow
from contexta.db.repositories import (
    activate_blueprint,
    create_project,
    fork_node,
    get_active_blueprint,
    get_insights_for_tags,
    get_node,
    get_project,
    list_blueprints,
    list_nodes_for_project,
    save_blueprint_version,
    upsert_insight,
    write_node,
)
from contexta.db.schema import init_database
from contexta.models.citations import SourceCitation
from contexta.models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from contexta.models.findings import IssueFinding
from contexta.models.payloads import ReviewNodePayload


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    """Provide a fresh in-memory aiosqlite connection for each test."""
    conn = await init_database(":memory:")
    yield conn
    await conn.close()


def _minimal_payload(dimension: ReviewDimensionEnum = ReviewDimensionEnum.RISK) -> ReviewNodePayload:
    return ReviewNodePayload(
        dimension=dimension,
        findings=[],
        overall_confidence=ConfidenceEnum.GREEN,
        raw_llm_response="{}",
    )


def _payload_with_finding() -> ReviewNodePayload:
    return ReviewNodePayload(
        dimension=ReviewDimensionEnum.SCOPE,
        findings=[
            IssueFinding(
                dimension=ReviewDimensionEnum.SCOPE,
                confidence=ConfidenceEnum.AMBER,
                summary="Scope is vague",
                detail="The scope section lacks measurable outcomes.",
                citations=[
                    SourceCitation(
                        file_path="docs/scope.md",
                        line_start=5,
                        line_end=12,
                        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
                        excerpt="Deliverables TBD",
                    )
                ],
                mitigation_routing=MitigationRoutingEnum.ASSUMPTIONS_MATRIX,
            )
        ],
        overall_confidence=ConfidenceEnum.AMBER,
        raw_llm_response='{"dimension":"Scope"}',
    )


# ─────────────────────────────────────────────────────────────────────────────
# Schema bootstrap tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schema_creates_all_tables(db) -> None:
    """All five tables must exist after init_database()."""
    expected = {
        "schema_version",
        "projects",
        "nodes",
        "prompt_blueprints",
        "global_client_insights",
    }
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    rows = await cursor.fetchall()
    actual = {r[0] for r in rows}
    assert expected.issubset(actual), f"Missing tables: {expected - actual}"


@pytest.mark.asyncio
async def test_nodes_table_has_version_tag_column(db) -> None:
    """nodes table must include the version_tag column per design constraint."""
    cursor = await db.execute("PRAGMA table_info(nodes)")
    rows = await cursor.fetchall()
    columns = {r[1] for r in rows}
    assert "version_tag" in columns, "version_tag column missing from nodes table"


@pytest.mark.asyncio
async def test_schema_version_is_recorded(db) -> None:
    from contexta.db.schema import SCHEMA_VERSION
    cursor = await db.execute("SELECT version FROM schema_version LIMIT 1")
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == SCHEMA_VERSION


@pytest.mark.asyncio
async def test_init_database_is_idempotent(tmp_path) -> None:
    """Calling init_database() twice on the same file must not raise."""
    db_path = str(tmp_path / "test.db")
    conn1 = await init_database(db_path)
    await conn1.close()
    conn2 = await init_database(db_path)
    await conn2.close()


# ─────────────────────────────────────────────────────────────────────────────
# Project CRUD
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_get_project(db) -> None:
    proj = await create_project(db, "Alpha Project", ["#Lean", "#Complex"])
    assert proj.name == "Alpha Project"
    assert proj.global_tags == ["#Lean", "#Complex"]

    fetched = await get_project(db, proj.id)
    assert fetched is not None
    assert fetched.id == proj.id
    assert fetched.name == proj.name
    assert fetched.global_tags == proj.global_tags


@pytest.mark.asyncio
async def test_get_project_missing_returns_none(db) -> None:
    result = await get_project(db, "nonexistent-id")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Node CRUD
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_and_get_node(db) -> None:
    proj = await create_project(db, "Test Project", [])
    payload = _minimal_payload()

    node = await write_node(
        db,
        project_id=proj.id,
        parent_id=None,
        layer_type="exploration",
        node_name="Baseline",
        payload=payload,
        metadata={"run": 1},
    )

    assert node.project_id == proj.id
    assert node.layer_type == "exploration"
    assert node.node_name == "Baseline"
    assert node.parent_id is None
    assert node.version_tag is None

    fetched = await get_node(db, node.id)
    assert fetched is not None
    assert fetched.id == node.id
    assert fetched.content_markdown == payload.model_dump_json()


@pytest.mark.asyncio
async def test_write_node_with_version_tag(db) -> None:
    proj = await create_project(db, "P", [])
    node = await write_node(
        db,
        project_id=proj.id,
        parent_id=None,
        layer_type="exploration",
        node_name="v1",
        payload=_minimal_payload(),
        metadata={},
        version_tag="v1.0-baseline",
    )
    assert node.version_tag == "v1.0-baseline"
    fetched = await get_node(db, node.id)
    assert fetched is not None
    assert fetched.version_tag == "v1.0-baseline"


@pytest.mark.asyncio
async def test_write_node_with_findings(db) -> None:
    proj = await create_project(db, "P2", [])
    payload = _payload_with_finding()
    node = await write_node(
        db,
        project_id=proj.id,
        parent_id=None,
        layer_type="exploration",
        node_name="Scope Review",
        payload=payload,
        metadata={},
    )
    # Re-parse content_markdown back to confirm round-trip fidelity
    fetched = await get_node(db, node.id)
    assert fetched is not None
    restored = ReviewNodePayload.model_validate_json(fetched.content_markdown)
    assert restored == payload


@pytest.mark.asyncio
async def test_list_nodes_for_project(db) -> None:
    proj = await create_project(db, "Listed", [])
    for dim in [ReviewDimensionEnum.RISK, ReviewDimensionEnum.SCOPE, ReviewDimensionEnum.INTENT]:
        await write_node(
            db, proj.id, None, "exploration", dim.value, _minimal_payload(dim), {}
        )

    nodes = await list_nodes_for_project(db, proj.id)
    assert len(nodes) == 3


@pytest.mark.asyncio
async def test_fork_node(db) -> None:
    proj = await create_project(db, "Fork Project", ["#tag"])
    parent = await write_node(
        db, proj.id, None, "exploration", "Parent", _minimal_payload(), {}
    )
    child = await fork_node(db, parent.id, "Fork-1", version_tag="fork-v1")

    assert child.project_id == parent.project_id
    assert child.parent_id == parent.id
    assert child.node_name == "Fork-1"
    assert child.version_tag == "fork-v1"
    assert child.content_markdown == ""
    assert child.metadata_json == {}


@pytest.mark.asyncio
async def test_fork_node_nonexistent_parent_raises(db) -> None:
    with pytest.raises(ValueError, match="not found"):
        await fork_node(db, "bad-id", "orphan")


# ─────────────────────────────────────────────────────────────────────────────
# Property 6 — DB Node Write Validation Guard
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_property6_mutated_payload_rejected_no_row_inserted(db) -> None:
    """
    Property 6: Constructing a valid payload then mutating it to an invalid
    state before calling write_node() raises ValidationError and leaves no
    row in the nodes table.
    """
    proj = await create_project(db, "Guard Test", [])

    # Build a valid payload, then corrupt its dimension field.
    payload = _minimal_payload()
    object.__setattr__(payload, "dimension", "NOT_A_VALID_DIMENSION")

    with pytest.raises((ValidationError, Exception)):
        await write_node(
            db,
            project_id=proj.id,
            parent_id=None,
            layer_type="exploration",
            node_name="Should Not Exist",
            payload=payload,
            metadata={},
        )

    # No rows must have been inserted.
    nodes = await list_nodes_for_project(db, proj.id)
    assert len(nodes) == 0, "write_node wrote a row despite validation failure"


@pytest.mark.asyncio
async def test_property6_invalid_confidence_rejected(db) -> None:
    """Invalid overall_confidence must prevent the DB write."""
    proj = await create_project(db, "Guard Test 2", [])
    payload = _minimal_payload()
    object.__setattr__(payload, "overall_confidence", "PURPLE")

    with pytest.raises((ValidationError, Exception)):
        await write_node(
            db, proj.id, None, "exploration", "bad", payload, {}
        )

    assert len(await list_nodes_for_project(db, proj.id)) == 0


@given(
    bad_dim=st.text(min_size=1).filter(
        lambda s: s not in {e.value for e in ReviewDimensionEnum}
    )
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_property6_arbitrary_invalid_dimension_rejected(bad_dim: str) -> None:
    """
    Property 6 (hypothesis): Any string that is not a valid ReviewDimensionEnum
    value causes the serialise-then-reparse guard in write_node to raise.
    """
    payload = _minimal_payload()
    object.__setattr__(payload, "dimension", bad_dim)

    raw = json.loads(payload.model_dump_json())
    raw["dimension"] = bad_dim

    with pytest.raises((ValidationError, Exception)):
        ReviewNodePayload.model_validate(raw)


# ─────────────────────────────────────────────────────────────────────────────
# Property 21 — One-Active Blueprint Invariant
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_property21_activate_blueprint_exactly_one_active(db) -> None:
    """
    Property 21: After activate_blueprint(id), exactly one row has is_active=1
    and its id equals the argument passed.
    """
    bp1 = await save_blueprint_version(db, "BP", "1.0", "Prompt v1")
    bp2 = await save_blueprint_version(db, "BP", "2.0", "Prompt v2")
    bp3 = await save_blueprint_version(db, "BP", "3.0", "Prompt v3")

    for target in [bp1, bp2, bp3]:
        await activate_blueprint(db, target.id)

        blueprints = await list_blueprints(db)
        active = [b for b in blueprints if b.is_active]
        assert len(active) == 1, (
            f"Expected exactly 1 active blueprint, got {len(active)} "
            f"after activating {target.id}"
        )
        assert active[0].id == target.id, (
            f"Active blueprint id {active[0].id!r} != target {target.id!r}"
        )


@pytest.mark.asyncio
async def test_property21_activate_from_corrupted_multi_active_state(db) -> None:
    """
    Property 21: Even if the database somehow has multiple is_active=1 rows
    (corrupted state), activate_blueprint() restores the invariant.
    """
    bp1 = await save_blueprint_version(db, "BP", "1.0", "P1")
    bp2 = await save_blueprint_version(db, "BP", "2.0", "P2")
    bp3 = await save_blueprint_version(db, "BP", "3.0", "P3")

    # Manually corrupt: set all three active simultaneously.
    await db.execute("UPDATE prompt_blueprints SET is_active = 1")
    await db.commit()

    corrupted = await list_blueprints(db)
    assert sum(1 for b in corrupted if b.is_active) == 3, "Pre-condition: 3 active"

    # Repair via activate_blueprint.
    await activate_blueprint(db, bp2.id)

    blueprints = await list_blueprints(db)
    active = [b for b in blueprints if b.is_active]
    assert len(active) == 1
    assert active[0].id == bp2.id


@pytest.mark.asyncio
async def test_property21_activate_nonexistent_blueprint_raises(db) -> None:
    """activate_blueprint with an unknown id must raise ValueError."""
    with pytest.raises(ValueError, match="not found"):
        await activate_blueprint(db, "does-not-exist")


@pytest.mark.asyncio
async def test_property21_single_blueprint_activates_correctly(db) -> None:
    """Edge case: activating the only blueprint in an empty table."""
    bp = await save_blueprint_version(db, "Solo", "1.0", "Solo prompt")
    await activate_blueprint(db, bp.id)

    active = await get_active_blueprint(db)
    assert active is not None
    assert active.id == bp.id
    assert active.is_active is True


@pytest.mark.asyncio
async def test_property21_get_active_blueprint_returns_none_when_none_set(db) -> None:
    """get_active_blueprint() returns None when no blueprint exists."""
    result = await get_active_blueprint(db)
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Blueprint management
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_blueprint_version_never_modifies_existing(db) -> None:
    """Each save_blueprint_version call must insert a new row, not update."""
    bp1 = await save_blueprint_version(db, "BP", "1.0", "Original")
    bp2 = await save_blueprint_version(db, "BP", "2.0", "Updated")

    assert bp1.id != bp2.id
    all_bps = await list_blueprints(db)
    assert len(all_bps) == 2

    # Original row still intact.
    assert all_bps[0].master_prompt_text == "Original"


@pytest.mark.asyncio
async def test_save_blueprint_version_starts_inactive(db) -> None:
    bp = await save_blueprint_version(db, "BP", "1.0", "Prompt")
    assert bp.is_active is False


# ─────────────────────────────────────────────────────────────────────────────
# Global Client Insights
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_insight_insert(db) -> None:
    row = await upsert_insight(db, "#Lean", "HIGH_RISK_TIMELINE")
    assert row.client_or_industry_tag == "#Lean"
    assert row.observed_pattern == "HIGH_RISK_TIMELINE"
    assert row.frequency_count == 1


@pytest.mark.asyncio
async def test_upsert_insight_increments_existing(db) -> None:
    await upsert_insight(db, "#Lean", "HIGH_RISK_TIMELINE")
    await upsert_insight(db, "#Lean", "HIGH_RISK_TIMELINE")
    row = await upsert_insight(db, "#Lean", "HIGH_RISK_TIMELINE")
    assert row.frequency_count == 3


@pytest.mark.asyncio
async def test_get_insights_for_tags_filters_correctly(db) -> None:
    await upsert_insight(db, "#Lean", "HIGH_RISK_TIMELINE")
    await upsert_insight(db, "#Complex", "HIGH_RISK_ARCHITECTURE")
    await upsert_insight(db, "#Other", "HIGH_RISK_SCOPE")

    results = await get_insights_for_tags(db, ["#Lean", "#Complex"])
    tags_found = {r.client_or_industry_tag for r in results}
    assert tags_found == {"#Lean", "#Complex"}


@pytest.mark.asyncio
async def test_get_insights_for_empty_tags_returns_empty(db) -> None:
    await upsert_insight(db, "#Tag", "PATTERN")
    results = await get_insights_for_tags(db, [])
    assert results == []
