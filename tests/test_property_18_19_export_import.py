"""Properties 18 & 19 — JSON Export/Import Round-Trip and Import Validation.

Property 18: For any complete JSONPacket, serialising to disk and importing
             via JSONPacketDeserializer produces an equivalent NodeRow, and
             schema_version is present and non-empty.

Property 19: For any JSON string that fails JSONPacket schema validation,
             import_packet() must raise ImportValidationError and leave the
             database tables unchanged.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from contexta.db.schema import init_database
from contexta.export.deserializer import ImportValidationError, JSONPacketDeserializer
from contexta.export.serializer import JSONPacketSerializer
from contexta.models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from contexta.models.export import EXPORT_SCHEMA_VERSION, ExportArbitratorResult, JSONPacket
from contexta.models.findings import IssueFinding
from contexta.models.citations import SourceCitation
from contexta.models.payloads import ReviewNodePayload


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_citation() -> SourceCitation:
    return SourceCitation(
        file_path="/doc.md",
        line_start=1,
        line_end=3,
        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
        excerpt="excerpt",
    )


def _make_finding(dim: ReviewDimensionEnum) -> IssueFinding:
    return IssueFinding(
        dimension=dim,
        confidence=ConfidenceEnum.AMBER,
        summary="Test summary",
        detail="Test detail",
        citations=[_make_citation()],
        mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
    )


def _make_payload(dim: ReviewDimensionEnum) -> ReviewNodePayload:
    return ReviewNodePayload(
        dimension=dim,
        findings=[_make_finding(dim)],
        overall_confidence=ConfidenceEnum.GREEN,
        raw_llm_response='{"ok": true}',
    )


def _make_full_packet() -> JSONPacket:
    """Build a complete JSONPacket with all 12 dimension payloads."""
    now = datetime.now(timezone.utc).isoformat()
    payloads = [_make_payload(dim) for dim in ReviewDimensionEnum]
    return JSONPacket(
        schema_version=EXPORT_SCHEMA_VERSION,
        project_id="project-test-001",
        project_name="Test Project",
        global_tags=["#Lean-Client"],
        node_id="node-test-001",
        node_name="Draft v1",
        parent_node_id=None,
        layer_type="exploration",
        payloads=payloads,
        arbitrator_result=ExportArbitratorResult(
            contradictions=[{"dimension_a": "Risk", "dimension_b": "Timeline", "description": "Conflict"}],
            raw_llm_response='{"contradictions": []}',
        ),
        routing_decisions=[],
        metadata={"extra": "data"},
        created_at=now,
    )


# ── Property 18: Round-trip ───────────────────────────────────────────────────


class TestProperty18ExportImportRoundTrip:

    @pytest.mark.asyncio
    async def test_round_trip_produces_node_row(self, tmp_path):
        """Serialise → write to disk → import → NodeRow exists."""
        packet = _make_full_packet()
        out_file = tmp_path / "packet.json"

        serializer = JSONPacketSerializer()
        await serializer.export(packet, out_file)

        assert out_file.exists(), "Output file must exist after export"

        db = await init_database(str(tmp_path / "test.db"))
        try:
            deserializer = JSONPacketDeserializer()
            node = await deserializer.import_packet(out_file, db)
            assert node.id is not None
            assert node.node_name == packet.node_name
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_schema_version_present_in_file(self, tmp_path):
        """Exported file must contain schema_version field."""
        packet = _make_full_packet()
        out_file = tmp_path / "packet.json"

        serializer = JSONPacketSerializer()
        await serializer.export(packet, out_file)

        raw = json.loads(out_file.read_text())
        assert "schema_version" in raw
        assert raw["schema_version"] != ""
        assert raw["schema_version"] == EXPORT_SCHEMA_VERSION

    @pytest.mark.asyncio
    async def test_dimension_payloads_preserved(self, tmp_path):
        """All 12 dimension payloads survive the round-trip."""
        packet = _make_full_packet()
        out_file = tmp_path / "packet.json"

        serializer = JSONPacketSerializer()
        await serializer.export(packet, out_file)

        raw = json.loads(out_file.read_text())
        assert len(raw["payloads"]) == 12

        # Re-validate each payload against the Pydantic model
        for payload_dict in raw["payloads"]:
            p = ReviewNodePayload.model_validate(payload_dict)
            assert p.dimension in ReviewDimensionEnum

    @pytest.mark.asyncio
    async def test_arbitrator_result_preserved(self, tmp_path):
        """Arbitrator result is preserved in the exported file."""
        packet = _make_full_packet()
        out_file = tmp_path / "packet.json"

        serializer = JSONPacketSerializer()
        await serializer.export(packet, out_file)

        raw = json.loads(out_file.read_text())
        assert raw["arbitrator_result"] is not None
        assert "contradictions" in raw["arbitrator_result"]

    @pytest.mark.asyncio
    async def test_no_tmp_file_remains_after_export(self, tmp_path):
        """No .tmp file should remain after a successful export."""
        packet = _make_full_packet()
        out_file = tmp_path / "packet.json"

        serializer = JSONPacketSerializer()
        await serializer.export(packet, out_file)

        tmp_file = out_file.with_suffix(".tmp")
        assert not tmp_file.exists(), ".tmp file must be cleaned up after move"

    @pytest.mark.asyncio
    async def test_metadata_fields_round_trip(self, tmp_path):
        """project_name, global_tags, node_name survive the file round-trip."""
        packet = _make_full_packet()
        out_file = tmp_path / "packet.json"

        serializer = JSONPacketSerializer()
        await serializer.export(packet, out_file)

        raw = json.loads(out_file.read_text())
        assert raw["project_name"] == packet.project_name
        assert raw["global_tags"] == packet.global_tags
        assert raw["node_name"] == packet.node_name
        assert raw["layer_type"] == packet.layer_type


# ── Property 19: No partial DB write on invalid import ────────────────────────


class TestProperty19ImportValidationNoPartialWrite:

    @pytest.mark.asyncio
    async def test_malformed_json_raises_import_validation_error(self, tmp_path):
        """Non-JSON content must raise ImportValidationError, not crash."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("this is not JSON at all", encoding="utf-8")

        db = await init_database(str(tmp_path / "test.db"))
        try:
            deserializer = JSONPacketDeserializer()
            with pytest.raises(ImportValidationError):
                await deserializer.import_packet(bad_file, db)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_missing_required_fields_raises_import_validation_error(self, tmp_path):
        """JSON missing required JSONPacket fields raises ImportValidationError."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text('{"schema_version": "1.0"}', encoding="utf-8")

        db = await init_database(str(tmp_path / "test.db"))
        try:
            deserializer = JSONPacketDeserializer()
            with pytest.raises(ImportValidationError):
                await deserializer.import_packet(bad_file, db)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_invalid_enum_in_payload_raises_import_validation_error(self, tmp_path):
        """Invalid enum value in dimension_payloads raises ImportValidationError."""
        bad_file = tmp_path / "bad.json"
        now = datetime.now(timezone.utc).isoformat()
        bad_data = {
            "schema_version": "1.0",
            "project_id": "project-bad-001",
            "project_name": "P",
            "global_tags": [],
            "node_id": "n1",
            "node_name": "N",
            "parent_node_id": None,
            "layer_type": "exploration",
            "payloads": [
                {
                    "dimension": "NONEXISTENT_DIMENSION",  # invalid enum
                    "findings": [],
                    "overall_confidence": "RED",
                    "raw_llm_response": "{}",
                }
            ],
            "arbitrator_result": None,
            "routing_decisions": [],
            "metadata": {},
            "created_at": now,
        }
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")

        db = await init_database(str(tmp_path / "test.db"))
        try:
            deserializer = JSONPacketDeserializer()
            with pytest.raises(ImportValidationError):
                await deserializer.import_packet(bad_file, db)
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_invalid_file_leaves_db_unchanged(self, tmp_path):
        """After a failed import, the nodes table must still be empty."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text('{"schema_version": "1.0"}', encoding="utf-8")

        db = await init_database(str(tmp_path / "test.db"))
        try:
            # Record initial row count
            async with db.execute("SELECT COUNT(*) FROM nodes") as cur:
                before = (await cur.fetchone())[0]

            deserializer = JSONPacketDeserializer()
            try:
                await deserializer.import_packet(bad_file, db)
            except ImportValidationError:
                pass

            async with db.execute("SELECT COUNT(*) FROM nodes") as cur:
                after = (await cur.fetchone())[0]

            assert after == before, (
                f"nodes table changed from {before} to {after} rows after failed import"
            )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_invalid_file_leaves_projects_unchanged(self, tmp_path):
        """After a failed import, the projects table must still be empty."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("CORRUPTED", encoding="utf-8")

        db = await init_database(str(tmp_path / "test.db"))
        try:
            async with db.execute("SELECT COUNT(*) FROM projects") as cur:
                before = (await cur.fetchone())[0]

            try:
                deserializer = JSONPacketDeserializer()
                await deserializer.import_packet(bad_file, db)
            except ImportValidationError:
                pass

            async with db.execute("SELECT COUNT(*) FROM projects") as cur:
                after = (await cur.fetchone())[0]

            assert after == before
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_missing_file_raises_import_validation_error(self, tmp_path):
        """Non-existent file must raise ImportValidationError."""
        db = await init_database(str(tmp_path / "test.db"))
        try:
            deserializer = JSONPacketDeserializer()
            with pytest.raises(ImportValidationError):
                await deserializer.import_packet(
                    tmp_path / "nonexistent.json", db
                )
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_valid_packet_is_accepted(self, tmp_path):
        """A valid JSONPacket round-trip does NOT raise ImportValidationError."""
        packet = _make_full_packet()
        out_file = tmp_path / "valid.json"

        serializer = JSONPacketSerializer()
        await serializer.export(packet, out_file)

        db = await init_database(str(tmp_path / "test.db"))
        try:
            deserializer = JSONPacketDeserializer()
            node = await deserializer.import_packet(out_file, db)
            assert node is not None
        finally:
            await db.close()
