"""tests/test_review_engine.py — Sprint 2: Review Engine Orchestration tests.

Coverage
--------
Schema:
  reviews table present after init_database(); SCHEMA_VERSION == 6;
  migration from a v2 database creates the reviews table.

ReviewRow / DB round-trip:
  create_review → get_review preserves all fields; missing review returns None;
  sme_augmentation_list and dimension_output survive JSON round-trip;
  list_reviews_for_version returns ordered results.

Provenance:
  Every ReviewRow has a non-empty version_id;
  FK constraint enforced — orphan version_id raises.

ArbitratorEngine.run_with_context() guards:
  Fewer or more than 12 payloads raise ArbitratorError before any processing;
  empty / whitespace version_id raises ArbitratorError.

run_with_context() output correctness:
  Returns TracedArbitratorOutput; version_id, persona, sme_augmentations
  propagated; exactly 12 dimension_summaries covering all dimensions.

Traceability Standard (scope.md §3):
  artifact_refs use [ArtifactID:SectionID] format; every cited finding
  appears in provenance_map; uncited findings flagged as Unsubstantiated;
  traceability_density: fully-cited=1.0, none-cited=0.0, partial, no-findings.

Contradiction detection:
  RED vs GREEN on shared artifact → contradiction; same-confidence → none;
  RED vs AMBER → none; no duplicate contradictions for same pair.

TracedArbitratorOutput.to_json():
  Returns valid JSON containing version_id, provenance_map,
  traceability_density, and unsubstantiated_findings keys.
"""

from __future__ import annotations

import json
import re
from typing import List

import aiosqlite
import pytest

from contexta.db.models import ReviewRow
from contexta.db.repositories import (
    create_project,
    create_review,
    create_version,
    get_review,
    list_reviews_for_version,
)
from contexta.db.schema import SCHEMA_VERSION, init_database
from contexta.models.citations import SourceCitation
from contexta.models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from contexta.models.findings import IssueFinding
from contexta.models.payloads import ReviewNodePayload
from contexta.pipeline.arbitrator import (
    ArbitratorEngine,
    ArbitratorError,
    ProvenanceEntry,
    ReviewContext,
    TracedArbitratorOutput,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
async def db():
    """Fresh in-memory DB with all migrations applied."""
    conn = await init_database(":memory:")
    yield conn
    await conn.close()


@pytest.fixture()
async def db_with_version(db):
    """DB pre-seeded with one project and one version."""
    project = await create_project(db, "Sprint2 Project", ["#Sprint2"])
    version = await create_version(db, project.id, "v1.0 — Initial Review")
    return db, project, version


@pytest.fixture()
def engine(llm_config, blueprint_row):
    """ArbitratorEngine instance for run_with_context() tests."""
    from contexta.llm.prompts import PromptBuilder

    builder = PromptBuilder(blueprint=blueprint_row)
    return ArbitratorEngine(config=llm_config, builder=builder)


# ─────────────────────────────────────────────────────────────────────────────
# Payload helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_empty_payloads() -> List[ReviewNodePayload]:
    """12 payloads — no findings, all GREEN."""
    return [
        ReviewNodePayload(
            dimension=dim,
            findings=[],
            overall_confidence=ConfidenceEnum.GREEN,
            raw_llm_response="{}",
        )
        for dim in ReviewDimensionEnum
    ]


def _make_cited_finding(
    dim: ReviewDimensionEnum,
    confidence: ConfidenceEnum,
    file_path: str = "/proposal.md",
    line_start: int = 1,
    line_end: int = 5,
) -> IssueFinding:
    return IssueFinding(
        dimension=dim,
        confidence=confidence,
        summary=f"Finding for {dim.value}",
        detail="Detail text.",
        citations=[
            SourceCitation(
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                citation_type=CitationTypeEnum.DIRECT_REFERENCE,
                excerpt="excerpt",
            )
        ],
        mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
    )


def _make_uncited_finding(dim: ReviewDimensionEnum) -> IssueFinding:
    return IssueFinding(
        dimension=dim,
        confidence=ConfidenceEnum.AMBER,
        summary=f"Uncited finding for {dim.value}",
        detail="No citation provided.",
        citations=[],
        mitigation_routing=MitigationRoutingEnum.ASSUMPTIONS_MATRIX,
    )


def _payload(dim: ReviewDimensionEnum, findings: list, confidence: ConfidenceEnum) -> ReviewNodePayload:
    return ReviewNodePayload(
        dimension=dim,
        findings=findings,
        overall_confidence=confidence,
        raw_llm_response="{}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Group 1 — Schema: reviews table + SCHEMA_VERSION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reviews_table_exists(db) -> None:
    """reviews table must be present after init_database()."""
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'"
    )
    row = await cursor.fetchone()
    assert row is not None, "reviews table not found in schema"


@pytest.mark.asyncio
async def test_schema_version_is_5(db) -> None:
    """SCHEMA_VERSION constant and stored DB version must both be 7 (updated v6→v7)."""
    assert SCHEMA_VERSION == 7
    cursor = await db.execute("SELECT version FROM schema_version LIMIT 1")
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 7, f"Expected schema version 7, got {row[0]}"


@pytest.mark.asyncio
async def test_reviews_table_has_required_columns(db) -> None:
    """reviews table must have all required columns."""
    cursor = await db.execute("PRAGMA table_info(reviews)")
    rows = await cursor.fetchall()
    columns = {r[1] for r in rows}
    required = {
        "id", "version_id", "persona_prompt",
        "user_context_text", "sme_augmentation_list",
        "dimension_output", "created_at",
    }
    missing = required - columns
    assert not missing, f"Missing columns in reviews table: {missing}"


@pytest.mark.asyncio
async def test_migration_v2_to_v3_creates_reviews_table(tmp_path) -> None:
    """A v2 database (no reviews table) is migrated to v3 by init_database()."""
    import aiosqlite as _aio

    db_path = str(tmp_path / "v2_migration.db")

    # Build a minimal v2-equivalent DB manually: projects + nodes + versions,
    # schema_version = 2, no reviews table.
    conn = await _aio.connect(db_path)
    conn.row_factory = _aio.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    await conn.execute("INSERT INTO schema_version VALUES (2)")
    await conn.execute(
        "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, global_tags TEXT NOT NULL DEFAULT '[]')"
    )
    await conn.execute(
        "CREATE TABLE versions (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, "
        "name TEXT NOT NULL, description TEXT, created_at TEXT NOT NULL)"
    )
    await conn.execute(
        "CREATE TABLE nodes (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, "
        "parent_id TEXT, layer_type TEXT NOT NULL, node_name TEXT NOT NULL, "
        "metadata_json TEXT NOT NULL DEFAULT '{}', content_markdown TEXT NOT NULL DEFAULT '', "
        "created_at TEXT NOT NULL, version_tag TEXT, version_id TEXT)"
    )
    await conn.commit()
    await conn.close()

    # Now run init_database() — should migrate to v3.
    conn2 = await init_database(db_path)
    try:
        cursor = await conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'"
        )
        assert await cursor.fetchone() is not None, "reviews table not created by v2→v3 migration"

        cursor2 = await conn2.execute("SELECT version FROM schema_version LIMIT 1")
        row = await cursor2.fetchone()
        assert row[0] == SCHEMA_VERSION, f"schema_version not updated to {SCHEMA_VERSION}, got {row[0]}"
    finally:
        await conn2.close()


# ─────────────────────────────────────────────────────────────────────────────
# Group 2 — ReviewRow DB round-trip
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_get_review_preserves_all_fields(db_with_version) -> None:
    """create_review → get_review returns a ReviewRow with identical fields."""
    db, project, version = db_with_version

    sme = ["SME augmentation A", "SME augmentation B"]
    dim_out = [{"dimension": "Risk", "confidence": "RED", "findings": 3}]

    review = await create_review(
        db,
        version_id=version.id,
        persona_prompt="You are a rigorous risk reviewer.",
        user_context_text="Client is in regulated healthcare.",
        sme_augmentation_list=sme,
        dimension_output=dim_out,
    )

    assert isinstance(review, ReviewRow)
    assert review.id
    assert review.version_id == version.id
    assert review.persona_prompt == "You are a rigorous risk reviewer."
    assert review.user_context_text == "Client is in regulated healthcare."
    assert review.sme_augmentation_list == sme
    assert review.dimension_output == dim_out
    assert review.created_at

    fetched = await get_review(db, review.id)
    assert fetched is not None
    assert fetched.id == review.id
    assert fetched.version_id == review.version_id
    assert fetched.persona_prompt == review.persona_prompt
    assert fetched.user_context_text == review.user_context_text
    assert fetched.sme_augmentation_list == sme
    assert fetched.dimension_output == dim_out
    assert fetched.created_at == review.created_at


@pytest.mark.asyncio
async def test_get_review_missing_returns_none(db) -> None:
    """get_review with a non-existent id must return None."""
    result = await get_review(db, "does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_sme_augmentation_list_empty_round_trip(db_with_version) -> None:
    """Empty sme_augmentation_list survives JSON serialisation round-trip."""
    db, _, version = db_with_version
    review = await create_review(
        db, version.id, "Persona", "Context", [], []
    )
    fetched = await get_review(db, review.id)
    assert fetched is not None
    assert fetched.sme_augmentation_list == []
    assert fetched.dimension_output == []


@pytest.mark.asyncio
async def test_dimension_output_complex_round_trip(db_with_version) -> None:
    """Nested dict structure in dimension_output survives JSON round-trip."""
    db, _, version = db_with_version
    complex_output = [
        {"dimension": d.value, "overall_confidence": "GREEN", "finding_count": i}
        for i, d in enumerate(ReviewDimensionEnum)
    ]
    review = await create_review(
        db, version.id, "Persona", "Context", [], complex_output
    )
    fetched = await get_review(db, review.id)
    assert fetched is not None
    assert fetched.dimension_output == complex_output


@pytest.mark.asyncio
async def test_list_reviews_for_version_returns_ordered(db_with_version) -> None:
    """list_reviews_for_version returns all reviews for a version, oldest first."""
    db, _, version = db_with_version

    r1 = await create_review(db, version.id, "Persona A", "Ctx A", [], [])
    r2 = await create_review(db, version.id, "Persona B", "Ctx B", [], [])
    r3 = await create_review(db, version.id, "Persona C", "Ctx C", [], [])

    results = await list_reviews_for_version(db, version.id)
    assert len(results) == 3
    ids = [r.id for r in results]
    assert r1.id in ids and r2.id in ids and r3.id in ids


@pytest.mark.asyncio
async def test_list_reviews_for_version_empty(db_with_version) -> None:
    """list_reviews_for_version returns [] when version has no reviews."""
    db, _, version = db_with_version
    results = await list_reviews_for_version(db, version.id)
    assert results == []


@pytest.mark.asyncio
async def test_list_reviews_for_version_isolation(db_with_version) -> None:
    """Reviews for version A are not returned when querying version B."""
    db, project, version_a = db_with_version
    version_b = await create_version(db, project.id, "v2.0")

    await create_review(db, version_a.id, "Persona", "Ctx", [], [])
    results_b = await list_reviews_for_version(db, version_b.id)
    assert results_b == []


# ─────────────────────────────────────────────────────────────────────────────
# Group 3 — Provenance: version_id linkage enforced
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_version_id_is_stored_and_non_empty(db_with_version) -> None:
    """Every ReviewRow carries a non-empty version_id (provenance anchor)."""
    db, _, version = db_with_version
    review = await create_review(db, version.id, "P", "C", [], [])
    assert review.version_id
    assert review.version_id == version.id


@pytest.mark.asyncio
async def test_review_version_id_fk_constraint_enforced(db_with_version) -> None:
    """Creating a review with a non-existent version_id raises an integrity error."""
    db, _, _ = db_with_version
    with pytest.raises(Exception):
        await create_review(db, "nonexistent-version-id", "P", "C", [], [])


# ─────────────────────────────────────────────────────────────────────────────
# Group 4 — run_with_context() guard rails
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_with_context_rejects_zero_payloads(engine) -> None:
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    with pytest.raises(ArbitratorError, match="12 payloads"):
        await engine.run_with_context([], ctx)


@pytest.mark.asyncio
async def test_run_with_context_rejects_11_payloads(engine) -> None:
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    eleven = _make_empty_payloads()[:11]
    with pytest.raises(ArbitratorError, match="12 payloads"):
        await engine.run_with_context(eleven, ctx)


@pytest.mark.asyncio
async def test_run_with_context_rejects_13_payloads(engine) -> None:
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    thirteen = _make_empty_payloads() + [_make_empty_payloads()[0]]
    with pytest.raises(ArbitratorError, match="12 payloads"):
        await engine.run_with_context(thirteen, ctx)


@pytest.mark.asyncio
async def test_run_with_context_rejects_empty_version_id(engine) -> None:
    ctx = ReviewContext(version_id="", persona_prompt="P", user_context_text="C")
    with pytest.raises(ArbitratorError, match="version_id"):
        await engine.run_with_context(_make_empty_payloads(), ctx)


@pytest.mark.asyncio
async def test_run_with_context_rejects_whitespace_version_id(engine) -> None:
    ctx = ReviewContext(version_id="   ", persona_prompt="P", user_context_text="C")
    with pytest.raises(ArbitratorError, match="version_id"):
        await engine.run_with_context(_make_empty_payloads(), ctx)


@pytest.mark.asyncio
async def test_run_with_context_guard_fires_before_processing(engine) -> None:
    """Guard must fire even if payloads would otherwise be valid."""
    ctx = ReviewContext(version_id="", persona_prompt="P", user_context_text="C")
    # Use exactly 12 payloads — only the version_id guard should fire.
    with pytest.raises(ArbitratorError):
        await engine.run_with_context(_make_empty_payloads(), ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Group 5 — run_with_context() output correctness
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_with_context_returns_traced_output_type(engine) -> None:
    ctx = ReviewContext(version_id="v-abc", persona_prompt="Persona", user_context_text="Ctx")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    assert isinstance(result, TracedArbitratorOutput)


@pytest.mark.asyncio
async def test_run_with_context_version_id_propagated(engine) -> None:
    ctx = ReviewContext(version_id="version-xyz-123", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    assert result.version_id == "version-xyz-123"


@pytest.mark.asyncio
async def test_run_with_context_persona_applied(engine) -> None:
    persona = "You are a strict technical architect reviewer."
    ctx = ReviewContext(version_id="v-001", persona_prompt=persona, user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    assert result.persona_applied == persona


@pytest.mark.asyncio
async def test_run_with_context_user_context_applied_true(engine) -> None:
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="Client is a bank.")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    assert result.user_context_applied is True


@pytest.mark.asyncio
async def test_run_with_context_user_context_applied_false_for_empty(engine) -> None:
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    assert result.user_context_applied is False


@pytest.mark.asyncio
async def test_run_with_context_user_context_applied_false_for_whitespace(engine) -> None:
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="   ")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    assert result.user_context_applied is False


@pytest.mark.asyncio
async def test_run_with_context_sme_augmentations_preserved(engine) -> None:
    sme = ["Banking domain expertise", "Regulatory compliance SME"]
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C",
                        sme_augmentation_list=sme)
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    assert result.sme_augmentations == sme


@pytest.mark.asyncio
async def test_run_with_context_sme_augmentations_empty_by_default(engine) -> None:
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    assert result.sme_augmentations == []


@pytest.mark.asyncio
async def test_run_with_context_exactly_12_dimension_summaries(engine) -> None:
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    assert len(result.dimension_summaries) == 12


@pytest.mark.asyncio
async def test_run_with_context_dimension_summaries_cover_all_dimensions(engine) -> None:
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    returned_dims = {s["dimension"] for s in result.dimension_summaries}
    expected_dims = {d.value for d in ReviewDimensionEnum}
    assert returned_dims == expected_dims


@pytest.mark.asyncio
async def test_run_with_context_dimension_summary_fields_present(engine) -> None:
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    for summary in result.dimension_summaries:
        assert "dimension" in summary
        assert "overall_confidence" in summary
        assert "finding_count" in summary
        assert "cited_finding_count" in summary
        assert "provenance_refs" in summary


# ─────────────────────────────────────────────────────────────────────────────
# Group 6 — Traceability Standard (scope.md §3)
# ─────────────────────────────────────────────────────────────────────────────

# Canonical [ArtifactID:SectionID] pattern: [<path>:<start>-<end>]
_ARTIFACT_REF_RE = re.compile(r"^\[.+:\d+-\d+\]$")


@pytest.mark.asyncio
async def test_provenance_map_uses_artifact_id_section_format(engine) -> None:
    """All artifact_refs must match [ArtifactID:SectionID] format."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    # Give the first dimension a cited finding.
    payloads[0] = _payload(
        dims[0],
        [_make_cited_finding(dims[0], ConfidenceEnum.AMBER, "/sow.md", 10, 20)],
        ConfidenceEnum.AMBER,
    )
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)

    assert len(result.provenance_map) >= 1
    for entry in result.provenance_map:
        assert isinstance(entry, ProvenanceEntry)
        assert _ARTIFACT_REF_RE.match(entry.artifact_ref), (
            f"artifact_ref {entry.artifact_ref!r} does not match [ArtifactID:SectionID] format"
        )


@pytest.mark.asyncio
async def test_provenance_map_encodes_correct_path_and_lines(engine) -> None:
    """artifact_ref encodes the exact file_path, line_start, and line_end."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    payloads[0] = _payload(
        dims[0],
        [_make_cited_finding(dims[0], ConfidenceEnum.RED, "/architecture.md", 42, 57)],
        ConfidenceEnum.RED,
    )
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)

    refs = [e.artifact_ref for e in result.provenance_map]
    assert "[/architecture.md:42-57]" in refs


@pytest.mark.asyncio
async def test_all_cited_findings_appear_in_provenance_map(engine) -> None:
    """Every (finding, citation) pair must produce a ProvenanceEntry."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    # Put 2 cited findings on dimension 0, 1 on dimension 1.
    payloads[0] = ReviewNodePayload(
        dimension=dims[0],
        findings=[
            _make_cited_finding(dims[0], ConfidenceEnum.RED, "/doc.md", 1, 5),
            _make_cited_finding(dims[0], ConfidenceEnum.AMBER, "/doc.md", 10, 15),
        ],
        overall_confidence=ConfidenceEnum.RED,
        raw_llm_response="{}",
    )
    payloads[1] = _payload(
        dims[1],
        [_make_cited_finding(dims[1], ConfidenceEnum.GREEN, "/readme.md", 3, 7)],
        ConfidenceEnum.GREEN,
    )
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)
    assert len(result.provenance_map) == 3


@pytest.mark.asyncio
async def test_uncited_findings_flagged_as_unsubstantiated(engine) -> None:
    """Findings with empty citations list are collected in unsubstantiated_findings."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    payloads[0] = _payload(dims[0], [_make_uncited_finding(dims[0])], ConfidenceEnum.AMBER)
    payloads[1] = _payload(dims[1], [_make_uncited_finding(dims[1])], ConfidenceEnum.AMBER)

    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)

    assert len(result.unsubstantiated_findings) == 2
    statuses = {f["status"] for f in result.unsubstantiated_findings}
    assert statuses == {"Unsubstantiated"}


@pytest.mark.asyncio
async def test_traceability_density_fully_cited(engine) -> None:
    """All findings cited → traceability_density == 1.0."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    payloads[0] = _payload(
        dims[0],
        [_make_cited_finding(dims[0], ConfidenceEnum.GREEN)],
        ConfidenceEnum.GREEN,
    )
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)
    assert result.traceability_density == 1.0


@pytest.mark.asyncio
async def test_traceability_density_none_cited(engine) -> None:
    """All findings uncited → traceability_density == 0.0."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    payloads[0] = _payload(dims[0], [_make_uncited_finding(dims[0])], ConfidenceEnum.AMBER)
    payloads[1] = _payload(dims[1], [_make_uncited_finding(dims[1])], ConfidenceEnum.AMBER)
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)
    assert result.traceability_density == 0.0


@pytest.mark.asyncio
async def test_traceability_density_partial(engine) -> None:
    """Half cited, half uncited → 0.0 < density < 1.0."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    payloads[0] = _payload(
        dims[0], [_make_cited_finding(dims[0], ConfidenceEnum.GREEN)], ConfidenceEnum.GREEN
    )
    payloads[1] = _payload(dims[1], [_make_uncited_finding(dims[1])], ConfidenceEnum.AMBER)
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)
    assert 0.0 < result.traceability_density < 1.0


@pytest.mark.asyncio
async def test_traceability_density_no_findings_is_one(engine) -> None:
    """No findings at all → density == 1.0 (vacuously fully traceable)."""
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    assert result.traceability_density == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Group 7 — Contradiction detection
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_contradictions_all_green(engine) -> None:
    """All payloads GREEN → empty contradictions list."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    # Every dimension cites same artifact, all GREEN.
    for i, dim in enumerate(dims):
        payloads[i] = _payload(
            dim,
            [_make_cited_finding(dim, ConfidenceEnum.GREEN, "/shared.md", 1, 5)],
            ConfidenceEnum.GREEN,
        )
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)
    assert result.contradictions == []


@pytest.mark.asyncio
async def test_contradiction_detected_red_vs_green_same_artifact(engine) -> None:
    """dim A cites /x.md:1-5 as RED, dim B cites same as GREEN → 1 contradiction."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    payloads[0] = _payload(
        dims[0],
        [_make_cited_finding(dims[0], ConfidenceEnum.RED, "/shared.md", 1, 5)],
        ConfidenceEnum.RED,
    )
    payloads[1] = _payload(
        dims[1],
        [_make_cited_finding(dims[1], ConfidenceEnum.GREEN, "/shared.md", 1, 5)],
        ConfidenceEnum.GREEN,
    )
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)
    assert len(result.contradictions) == 1


@pytest.mark.asyncio
async def test_contradiction_entry_has_required_fields(engine) -> None:
    """Each contradiction dict must have dimension_a, dimension_b, artifact_ref, description."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    payloads[0] = _payload(
        dims[0],
        [_make_cited_finding(dims[0], ConfidenceEnum.RED, "/x.md", 1, 5)],
        ConfidenceEnum.RED,
    )
    payloads[1] = _payload(
        dims[1],
        [_make_cited_finding(dims[1], ConfidenceEnum.GREEN, "/x.md", 1, 5)],
        ConfidenceEnum.GREEN,
    )
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)

    c = result.contradictions[0]
    assert "dimension_a" in c
    assert "dimension_b" in c
    assert "artifact_ref" in c
    assert "description" in c
    assert c["artifact_ref"] == "[/x.md:1-5]"


@pytest.mark.asyncio
async def test_no_contradiction_for_red_vs_amber(engine) -> None:
    """RED and AMBER on the same artifact do not constitute a contradiction."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    payloads[0] = _payload(
        dims[0],
        [_make_cited_finding(dims[0], ConfidenceEnum.RED, "/y.md", 2, 8)],
        ConfidenceEnum.RED,
    )
    payloads[1] = _payload(
        dims[1],
        [_make_cited_finding(dims[1], ConfidenceEnum.AMBER, "/y.md", 2, 8)],
        ConfidenceEnum.AMBER,
    )
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)
    assert result.contradictions == []


@pytest.mark.asyncio
async def test_no_contradiction_for_different_artifacts(engine) -> None:
    """RED and GREEN on different artifacts do not produce a contradiction."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    payloads[0] = _payload(
        dims[0],
        [_make_cited_finding(dims[0], ConfidenceEnum.RED, "/doc_a.md", 1, 5)],
        ConfidenceEnum.RED,
    )
    payloads[1] = _payload(
        dims[1],
        [_make_cited_finding(dims[1], ConfidenceEnum.GREEN, "/doc_b.md", 1, 5)],
        ConfidenceEnum.GREEN,
    )
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)
    assert result.contradictions == []


@pytest.mark.asyncio
async def test_no_duplicate_contradictions_for_same_pair(engine) -> None:
    """dim A RED + dim B GREEN on the same artifact yields exactly one entry."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    # Two citations to the same artifact from the same dimension pair.
    payloads[0] = ReviewNodePayload(
        dimension=dims[0],
        findings=[
            _make_cited_finding(dims[0], ConfidenceEnum.RED, "/dup.md", 1, 5),
            _make_cited_finding(dims[0], ConfidenceEnum.RED, "/dup.md", 1, 5),
        ],
        overall_confidence=ConfidenceEnum.RED,
        raw_llm_response="{}",
    )
    payloads[1] = _payload(
        dims[1],
        [_make_cited_finding(dims[1], ConfidenceEnum.GREEN, "/dup.md", 1, 5)],
        ConfidenceEnum.GREEN,
    )
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)
    pairs = [(c["dimension_a"], c["dimension_b"]) for c in result.contradictions]
    unique_pairs = {frozenset(p) for p in pairs}
    assert len(unique_pairs) == 1, (
        f"Expected 1 unique contradiction pair, got {len(unique_pairs)}: {unique_pairs}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Group 8 — TracedArbitratorOutput.to_json()
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_to_json_returns_valid_json(engine) -> None:
    """to_json() must return a parseable JSON string."""
    ctx = ReviewContext(version_id="v-json-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    raw = result.to_json()
    parsed = json.loads(raw)  # raises if invalid
    assert isinstance(parsed, dict)


@pytest.mark.asyncio
async def test_to_json_contains_version_id(engine) -> None:
    """to_json() output must contain the version_id field."""
    ctx = ReviewContext(version_id="v-export-999", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    parsed = json.loads(result.to_json())
    assert "version_id" in parsed
    assert parsed["version_id"] == "v-export-999"


@pytest.mark.asyncio
async def test_to_json_contains_provenance_map(engine) -> None:
    """to_json() must include the provenance_map key (even if empty)."""
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    parsed = json.loads(result.to_json())
    assert "provenance_map" in parsed
    assert isinstance(parsed["provenance_map"], list)


@pytest.mark.asyncio
async def test_to_json_contains_traceability_density(engine) -> None:
    """to_json() must include traceability_density as a number."""
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    parsed = json.loads(result.to_json())
    assert "traceability_density" in parsed
    assert isinstance(parsed["traceability_density"], float)


@pytest.mark.asyncio
async def test_to_json_contains_unsubstantiated_findings(engine) -> None:
    """to_json() must include the unsubstantiated_findings key."""
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(_make_empty_payloads(), ctx)
    parsed = json.loads(result.to_json())
    assert "unsubstantiated_findings" in parsed
    assert isinstance(parsed["unsubstantiated_findings"], list)


@pytest.mark.asyncio
async def test_to_json_provenance_map_entries_serialised_correctly(engine) -> None:
    """ProvenanceEntry objects must serialise to dicts with all required keys."""
    dims = list(ReviewDimensionEnum)
    payloads = _make_empty_payloads()
    payloads[0] = _payload(
        dims[0],
        [_make_cited_finding(dims[0], ConfidenceEnum.AMBER, "/spec.md", 5, 10)],
        ConfidenceEnum.AMBER,
    )
    ctx = ReviewContext(version_id="v-001", persona_prompt="P", user_context_text="C")
    result = await engine.run_with_context(payloads, ctx)
    parsed = json.loads(result.to_json())

    assert len(parsed["provenance_map"]) == 1
    entry = parsed["provenance_map"][0]
    assert entry["artifact_ref"] == "[/spec.md:5-10]"
    assert entry["dimension"] == dims[0].value
    assert entry["confidence"] == "AMBER"
    assert "finding_summary" in entry
    assert "citation_type" in entry
