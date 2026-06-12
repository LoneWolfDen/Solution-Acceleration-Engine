"""JSON Packet Deserializer — schema validation + all-or-nothing DB import.

Design contracts
----------------
- ``import_packet()`` validates the file against ``JSONPacket`` BEFORE writing
  anything to the database.  If validation fails, ``ImportValidationError`` is
  raised and no rows are inserted (Property 19).
- The DB write is performed inside a single transaction so the import is
  all-or-nothing (Requirement 12.3).
"""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite
from pydantic import ValidationError

from ..db.models import NodeRow
from ..db.repositories import create_project, get_project, write_node
from ..models.export import JSONPacket
from ..models.payloads import ReviewNodePayload


# ── Exception ─────────────────────────────────────────────────────────────────


class ImportValidationError(Exception):
    """Raised when an imported JSON file fails ``JSONPacket`` schema validation."""


# ── Deserializer ──────────────────────────────────────────────────────────────


class JSONPacketDeserializer:
    """Imports a previously exported JSON Packet into the database."""

    async def import_packet(
        self,
        file_path: Path,
        conn: aiosqlite.Connection,
    ) -> NodeRow:
        """Read, validate, and import a ``JSONPacket`` from disk.

        Steps
        -----
        1. Read the file from disk.
        2. Validate against ``JSONPacket`` schema — raise
           ``ImportValidationError`` on failure (NO DB write).
        3. Ensure the project exists (create if absent).
        4. Write the node row in a single all-or-nothing transaction.

        Parameters
        ----------
        file_path:
            Path to the exported ``.json`` file.
        conn:
            Open database connection.

        Returns
        -------
        NodeRow
            The newly created node row.

        Raises
        ------
        ImportValidationError
            If the file cannot be read or fails schema validation.
        """
        # Step 1 — read
        try:
            raw = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ImportValidationError(f"Cannot read file {file_path!r}: {exc}") from exc

        # Step 2 — validate (NO DB write on failure)
        try:
            packet = JSONPacket.model_validate_json(raw)
        except ValidationError as exc:
            raise ImportValidationError(
                f"JSON Packet failed schema validation: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ImportValidationError(
                f"JSON Packet is not valid JSON: {exc}"
            ) from exc

        # Step 3 — ensure project exists
        project = await get_project(conn, packet.project_id)
        if project is None:
            project = await create_project(
                conn,
                name=packet.project_name,
                global_tags=packet.global_tags,
            )

        # Step 4 — build representative payload and metadata, then write node
        payloads = packet.payloads
        if not payloads:
            raise ImportValidationError(
                "JSONPacket contains no payloads; cannot import."
            )

        metadata: dict = {
            "dimensions": [p.model_dump() for p in payloads],
            "routing_decisions": packet.routing_decisions,
            "imported_from": str(file_path),
            "schema_version": packet.schema_version,
            **packet.metadata,
        }
        if packet.arbitrator_result is not None:
            metadata["arbitrator_result"] = packet.arbitrator_result.model_dump()

        node_row = await write_node(
            conn,
            project_id=project.id,
            parent_id=packet.parent_node_id,
            layer_type=packet.layer_type,
            node_name=packet.node_name,
            payload=payloads[0],
            metadata=metadata,
            version_tag=packet.version_tag,
        )
        return node_row
