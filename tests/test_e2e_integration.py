"""End-to-End Workspace Verification — integration sweep.

Proves a solution proposal can move successfully from:
  1. Raw file ingest (MCPHostClient + ArtifactRegistry)
  2. Through unified 12-dimension LLM review (TaskOrchestrator, mocked LLM)
  3. To a final synthesis node creation (ArbitratorEngine + DB commit)

All external I/O (LLM calls, MCP server) is mocked; the real SQLite DB,
Pydantic validation pipeline, and all business-logic modules run for real.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contexta.admin.blueprint_manager import PromptBlueprintManager
from contexta.admin.dream_cycle import DreamCycleWorker
from contexta.db.repositories import (
    activate_blueprint,
    create_project,
    get_node,
    list_nodes_for_project,
    save_blueprint_version,
)
from contexta.db.schema import init_database
from contexta.export.deserializer import JSONPacketDeserializer
from contexta.export.serializer import JSONPacketSerializer
from contexta.llm.provider import LLMConfig
from contexta.mcp.artifact_registry import ArtifactRegistry
from contexta.mcp.client import MCPHostClient
from contexta.models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from contexta.models.export import EXPORT_SCHEMA_VERSION, JSONPacket
from contexta.models.findings import IssueFinding
from contexta.models.citations import SourceCitation
from contexta.models.payloads import ReviewNodePayload
from contexta.pipeline.arbitrator import ArbitratorEngine
from contexta.pipeline.dimension_runner import (
    TaskOrchestrator,
    TaskState,
    commit_exploration_node,
    make_dimension_runner,
)


# ── LLM mock factory ──────────────────────────────────────────────────────────
# Factories are centralised in tests/fixtures.py; imported here so this module
# stays thin and the mock contract has a single source of truth.

from tests.fixtures import (
    make_acompletion_sequential_mock as _make_acompletion_sequential_mock,
    make_arbitrator_response as _make_arbitrator_response,
    make_dimension_llm_response as _make_dimension_llm_response,
)


# ── Fixture: in-memory DB ─────────────────────────────────────────────────────


@pytest.fixture()
async def db(tmp_path):
    conn = await init_database(str(tmp_path / "e2e_test.db"))
    yield conn
    await conn.close()


@pytest.fixture()
async def seeded_db(db):
    """DB with an active blueprint and a project."""
    bp = await save_blueprint_version(
        db,
        name="E2E Blueprint",
        version="1.0.0",
        prompt_text="Review this proposal rigorously.",
    )
    await activate_blueprint(db, bp.id)
    project = await create_project(db, "E2E Test Project", ["#E2E", "#Integration"])
    return db, bp, project


# ── E2E Test 1: Full ingest → Layer 1 → DB commit ────────────────────────────


class TestE2EFullPipeline:

    @pytest.mark.asyncio
    async def test_ingest_and_layer1_completes(self, seeded_db, tmp_path):
        """Full flow: ingest file → launch 12 dimensions → all COMPLETE → DB write."""
        db, bp, project = seeded_db

        # Step 1: Ingest a mock file
        registry = ArtifactRegistry()
        client = MCPHostClient(registry)

        content_item = MagicMock()
        content_item.text = "This is a proposal document.\nLine two.\nLine three.\n"
        read_result = MagicMock()
        read_result.contents = [content_item]
        mock_session = MagicMock()
        mock_session.read_resource = AsyncMock(return_value=read_result)
        client._session = mock_session

        artifact = await client.ingest_file("file:///proposal.md")
        assert artifact.line_count == 3
        assert len(registry) == 1

        # Step 2: Build the runner (mock LLM)
        from contexta.llm.prompts import PromptBuilder

        builder = PromptBuilder(
            blueprint=bp,
        )

        state_changes: list[TaskState] = []

        async def _on_state_change(task) -> None:
            state_changes.append(task.state)

        with patch(
            "contexta.llm.provider.litellm.acompletion",
            _make_acompletion_sequential_mock(),
        ):
            runner_fn = make_dimension_runner(
                config=LLMConfig(model="ollama/mistral"),
                builder=builder,
                registry=registry,
            )
            orchestrator = TaskOrchestrator(
                on_state_change=_on_state_change,
                runner_fn=runner_fn,
            )

            # Step 3: Launch all 12 dimensions
            await orchestrator.launch_all()

        assert orchestrator.all_complete(), (
            f"Not all complete: {orchestrator.incomplete_dimensions()}"
        )

        # Step 4: Batch-commit to DB
        node = await commit_exploration_node(
            orchestrator,
            db,
            project_id=project.id,
            node_name="E2E Exploration v1",
        )
        assert node.id is not None
        assert node.layer_type == "exploration"
        assert node.project_id == project.id

        # Step 5: Verify DB contains the node
        fetched = await get_node(db, node.id)
        assert fetched is not None
        metadata = json.loads(fetched.metadata_json)
        assert len(metadata["dimensions"]) == 12

    @pytest.mark.asyncio
    async def test_layer1_state_transitions(self, seeded_db):
        """Every dimension transitions through PENDING → RUNNING → COMPLETE."""
        db, bp, project = seeded_db

        registry = ArtifactRegistry()
        from contexta.mcp.artifact_registry import IngestedArtifact
        registry.register(IngestedArtifact(
            uri="file:///doc.md",
            file_path="/doc.md",
            content="test content\n",
            line_count=1,
        ))

        from contexta.llm.prompts import PromptBuilder
        builder = PromptBuilder(blueprint=bp)

        transitions: dict[str, list[str]] = {}

        async def _on_state_change(task) -> None:
            key = task.dimension.value
            if key not in transitions:
                transitions[key] = []
            transitions[key].append(task.state.value)

        with patch(
            "contexta.llm.provider.litellm.acompletion",
            _make_acompletion_sequential_mock(),
        ):
            runner_fn = make_dimension_runner(
                config=LLMConfig(model="ollama/mistral"),
                builder=builder,
                registry=registry,
            )
            orchestrator = TaskOrchestrator(
                on_state_change=_on_state_change,
                runner_fn=runner_fn,
            )
            await orchestrator.launch_all()

        # Every dimension should have received at least RUNNING and COMPLETE
        for dim in ReviewDimensionEnum:
            assert dim.value in transitions
            assert "RUNNING" in transitions[dim.value]
            assert "COMPLETE" in transitions[dim.value]


# ── E2E Test 2: Layer 2 Arbitrator ───────────────────────────────────────────


class TestE2EArbitrator:

    @pytest.mark.asyncio
    async def test_arbitrator_detects_contradictions(self, seeded_db):
        """Arbitrator runs on 12 payloads and returns contradictions."""
        db, bp, project = seeded_db

        payloads = [
            ReviewNodePayload(
                dimension=dim,
                findings=[],
                overall_confidence=ConfidenceEnum.GREEN,
                raw_llm_response="{}",
            )
            for dim in ReviewDimensionEnum
        ]

        from contexta.llm.prompts import PromptBuilder
        builder = PromptBuilder(blueprint=bp)
        engine = ArbitratorEngine(
            config=LLMConfig(model="ollama/mistral"),
            builder=builder,
        )

        arb_choice = MagicMock()
        arb_choice.message.content = _make_arbitrator_response()
        arb_choice.finish_reason = "stop"
        arb_response = MagicMock()
        arb_response.choices = [arb_choice]

        with patch(
            "contexta.llm.provider.litellm.acompletion",
            AsyncMock(return_value=arb_response),
        ):
            result = await engine.run(payloads)

        assert len(result.contradictions) == 1
        assert result.contradictions[0]["dimension_a"] == "Risk"

    @pytest.mark.asyncio
    async def test_arbitrator_rejects_fewer_than_12_payloads(self, seeded_db):
        """Arbitrator raises ArbitratorError for < 12 payloads."""
        db, bp, project = seeded_db

        from contexta.pipeline.arbitrator import ArbitratorError
        from contexta.llm.prompts import PromptBuilder
        builder = PromptBuilder(blueprint=bp)
        engine = ArbitratorEngine(
            config=LLMConfig(model="ollama/mistral"),
            builder=builder,
        )

        with pytest.raises(ArbitratorError, match="12 payloads"):
            await engine.run([])


# ── E2E Test 3: Export → Import → Dream Cycle ────────────────────────────────


class TestE2EExportImportDreamCycle:

    @pytest.mark.asyncio
    async def test_full_export_import_cycle(self, seeded_db, tmp_path):
        """Export a packet → import it → Dream Cycle finds pattern."""
        db, bp, project = seeded_db

        # Build a packet with a RED finding
        dim = ReviewDimensionEnum.RISK
        payload = ReviewNodePayload(
            dimension=dim,
            findings=[
                IssueFinding(
                    dimension=dim,
                    confidence=ConfidenceEnum.RED,
                    summary="Critical risk",
                    detail="This is a critical risk",
                    citations=[
                        SourceCitation(
                            file_path="/proposal.md",
                            line_start=1,
                            line_end=2,
                            citation_type=CitationTypeEnum.DIRECT_REFERENCE,
                            excerpt="risk excerpt",
                        )
                    ],
                    mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
                )
            ],
            overall_confidence=ConfidenceEnum.RED,
            raw_llm_response="{}",
        )

        # Fill remaining 11 payloads as GREEN
        all_payloads = [payload]
        for d in ReviewDimensionEnum:
            if d != dim:
                all_payloads.append(
                    ReviewNodePayload(
                        dimension=d,
                        findings=[],
                        overall_confidence=ConfidenceEnum.GREEN,
                        raw_llm_response="{}",
                    )
                )

        now = datetime.now(timezone.utc).isoformat()
        packet = JSONPacket(
            schema_version=EXPORT_SCHEMA_VERSION,
            project_id=project.id,
            project_name=project.name,
            global_tags=project.global_tags,
            node_id=str(uuid.uuid4()),
            node_name="E2E Node",
            parent_node_id=None,
            layer_type="exploration",
            payloads=all_payloads,
            arbitrator_result=None,
            routing_decisions=[],
            metadata={},
            created_at=now,
        )

        # Export to disk
        out_file = tmp_path / "e2e_packet.json"
        serializer = JSONPacketSerializer()
        await serializer.export(packet, out_file)
        assert out_file.exists()

        # Import into a fresh DB
        db2 = await init_database(str(tmp_path / "import_test.db"))
        try:
            deserializer = JSONPacketDeserializer()
            node = await deserializer.import_packet(out_file, db2)
            assert node is not None

            # Manually insert the project and node for Dream Cycle
            # (deserializer creates project and node — now run Dream Cycle)
            worker = DreamCycleWorker()
            count = await worker.run(db2)
            # The imported node has RED confidence in RISK dimension
            # Project tags are ["#E2E", "#Integration"]
            assert count >= 1, f"Expected ≥1 Dream Cycle insight, got {count}"
        finally:
            await db2.close()

    @pytest.mark.asyncio
    async def test_db_repositories_upsert_idempotency(self, db):
        """upsert_insight increments count on repeated calls."""
        from contexta.db.repositories import upsert_insight

        r1 = await upsert_insight(db, "#TagTest", "HIGH_RISK_SCOPE")
        assert r1.frequency_count == 1

        r2 = await upsert_insight(db, "#TagTest", "HIGH_RISK_SCOPE")
        assert r2.frequency_count == 2

        r3 = await upsert_insight(db, "#TagTest", "HIGH_RISK_SCOPE")
        assert r3.frequency_count == 3

    @pytest.mark.asyncio
    async def test_fork_node_creates_new_node(self, seeded_db):
        """fork_node creates a child node with correct parent linkage."""
        db, bp, project = seeded_db

        # Create a base node first
        from contexta.db.repositories import fork_node, write_node
        payload = ReviewNodePayload(
            dimension=ReviewDimensionEnum.INTENT,
            findings=[],
            overall_confidence=ConfidenceEnum.GREEN,
            raw_llm_response="{}",
        )
        parent = await write_node(
            db,
            project_id=project.id,
            parent_id=None,
            layer_type="exploration",
            node_name="Parent Node",
            payload=payload,
            metadata={"dimensions": [], "routing_decisions": []},
        )

        child = await fork_node(db, parent.id, "Forked Node")
        assert child.parent_id == parent.id
        assert child.project_id == project.id
        assert child.node_name == "Forked Node"


# ── E2E Test 4: Scope Policy ─────────────────────────────────────────────────


class TestE2EScopePolicy:

    def test_scope_findings_extraction(self):
        """ScopePolicyEnforcer extracts only SCOPE_MODIFICATION findings."""
        from contexta.pipeline.scope_policy import ScopePolicyEnforcer

        enforcer = ScopePolicyEnforcer()

        scope_finding = IssueFinding(
            dimension=ReviewDimensionEnum.SCOPE,
            confidence=ConfidenceEnum.RED,
            summary="Scope issue",
            detail="Detail",
            citations=[],
            mitigation_routing=MitigationRoutingEnum.SCOPE_MODIFICATION,
        )
        risk_finding = IssueFinding(
            dimension=ReviewDimensionEnum.RISK,
            confidence=ConfidenceEnum.AMBER,
            summary="Risk issue",
            detail="Detail",
            citations=[],
            mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
        )

        payloads = [
            ReviewNodePayload(
                dimension=ReviewDimensionEnum.SCOPE,
                findings=[scope_finding],
                overall_confidence=ConfidenceEnum.RED,
                raw_llm_response="{}",
            ),
            ReviewNodePayload(
                dimension=ReviewDimensionEnum.RISK,
                findings=[risk_finding],
                overall_confidence=ConfidenceEnum.AMBER,
                raw_llm_response="{}",
            ),
        ]

        scope_findings = enforcer.get_scope_findings(payloads)
        assert len(scope_findings) == 1
        assert scope_findings[0].mitigation_routing == MitigationRoutingEnum.SCOPE_MODIFICATION

    def test_routing_decision_recorded_in_metadata(self):
        """apply_routing_decision appends to routing_decisions list."""
        from contexta.pipeline.scope_policy import ScopePolicyEnforcer

        enforcer = ScopePolicyEnforcer()
        finding = IssueFinding(
            dimension=ReviewDimensionEnum.SCOPE,
            confidence=ConfidenceEnum.RED,
            summary="Scope change needed",
            detail="Detail",
            citations=[],
            mitigation_routing=MitigationRoutingEnum.SCOPE_MODIFICATION,
        )
        metadata: dict = {"routing_decisions": []}
        updated = enforcer.apply_routing_decision(
            finding, MitigationRoutingEnum.RISK_REGISTER, metadata
        )
        assert len(updated["routing_decisions"]) == 1
        assert updated["routing_decisions"][0]["new_routing"] == "Risk Register"
        assert updated["routing_decisions"][0]["dimension"] == "Scope"


# ── E2E Test 5: Blueprint Manager ────────────────────────────────────────────


class TestE2EBlueprintManager:

    @pytest.mark.asyncio
    async def test_one_active_blueprint_invariant(self, db):
        """Activating a blueprint deactivates all others."""
        manager = PromptBlueprintManager(db)

        bp1 = await manager.save_new_version("BP1", "1.0", "prompt one")
        bp2 = await manager.save_new_version("BP2", "1.0", "prompt two")
        bp3 = await manager.save_new_version("BP3", "1.0", "prompt three")

        await manager.activate(bp1.id)
        active = await manager.get_active()
        assert active is not None
        assert active.id == bp1.id

        await manager.activate(bp2.id)
        active = await manager.get_active()
        assert active.id == bp2.id

        all_bps = await manager.list_all()
        active_bps = [bp for bp in all_bps if bp.is_active]
        assert len(active_bps) == 1, (
            f"Expected exactly 1 active blueprint, found {len(active_bps)}"
        )

    @pytest.mark.asyncio
    async def test_new_version_does_not_modify_existing(self, db):
        """save_new_version never modifies an existing blueprint row."""
        manager = PromptBlueprintManager(db)
        original = await manager.save_new_version("BP", "1.0", "original text")

        new_version = await manager.save_new_version("BP", "2.0", "updated text")

        all_bps = await manager.list_all()
        originals = [bp for bp in all_bps if bp.id == original.id]
        assert len(originals) == 1
        assert originals[0].master_prompt_text == "original text"
        assert originals[0].version_string == "1.0"
