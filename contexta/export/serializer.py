"""JSON Packet Serializer — cross-device-safe atomic export.

Uses ``shutil.move()`` instead of ``Path.rename()`` to guarantee atomicity
across Docker volume mount boundaries where ``os.rename()`` would raise
``EXDEV`` (cross-device link error).

Design contracts
----------------
- Writes to a ``.tmp`` file in the same parent directory first.
- Calls ``shutil.move(str(tmp), str(output))`` for the atomic promotion.
- On any ``OSError``, deletes the ``.tmp`` file if it exists and raises
  ``ExportError`` — no partial file is left on disk (Requirement 11.5).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..models.export import JSONPacket


# ── Exception ─────────────────────────────────────────────────────────────────


class ExportError(Exception):
    """Raised when the JSON packet export fails due to a filesystem error."""


# ── Serializer ────────────────────────────────────────────────────────────────


class JSONPacketSerializer:
    """Serializes a ``JSONPacket`` to disk using an atomic write pattern."""

    async def export(self, packet: JSONPacket, output_path: Path) -> None:
        """Write *packet* to *output_path* as pretty-printed JSON.

        Parameters
        ----------
        packet:
            The fully populated ``JSONPacket`` to serialize.
        output_path:
            Destination file path (will be created or overwritten).

        Raises
        ------
        ExportError
            On any filesystem error.  No partial file is left on disk.
        """
        output_path = Path(output_path)
        tmp_path = output_path.with_suffix(".tmp")

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(
                packet.model_dump_json(indent=2),
                encoding="utf-8",
            )
            shutil.move(str(tmp_path), str(output_path))
        except OSError as exc:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise ExportError(f"Export failed: {exc}") from exc
