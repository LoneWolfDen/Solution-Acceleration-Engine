"""Dream Cycle Worker — background pattern aggregation.

Uses SQLite's ``json_each()`` table-valued function to extract RED-confidence
dimension entries directly within the database execution layer, avoiding
full Python-level blob deserialization for nodes that have no RED findings.

Design contracts
----------------
- ``run()`` executes a single ``json_each()`` query and iterates only the
  filtered ``(global_tags, dimension_name)`` result rows.
- Per-row errors are logged but do NOT abort the cycle (Requirement 13.6).
- Returns the count of insight rows created or updated.
- Monotonicity: re-running on the same data never decreases any
  ``frequency_count`` (Property 20 — guaranteed by the UPSERT increment).
"""

from __future__ import annotations

import json
import logging

import aiosqlite

from ..db.repositories import upsert_insight

logger = logging.getLogger(__name__)

# SQL query using json_each() to push filtering into SQLite (design §12.1)
_EXTRACT_RED_SQL = """
    SELECT
        p.global_tags                                        AS global_tags,
        json_extract(dim.value, '$.dimension')               AS dimension_name
    FROM nodes n
    JOIN projects p ON p.id = n.project_id
    JOIN json_each(n.metadata_json, '$.dimensions') AS dim
    WHERE n.layer_type = 'exploration'
      AND json_extract(dim.value, '$.overall_confidence') = 'RED'
"""


class DreamCycleWorker:
    """Analyses the global nodes table for recurring RED-confidence patterns.

    Intended to be launched as a Textual ``Worker`` (``@work(exclusive=True,
    thread=False)``) from the Admin Screen so it runs in the asyncio event
    loop without blocking the TUI.
    """

    async def run(self, conn: aiosqlite.Connection) -> int:
        """Execute the Dream Cycle analysis.

        Parameters
        ----------
        conn:
            Open database connection (read + write access required).

        Returns
        -------
        int
            Number of insight rows created or updated during this run.
        """
        updated = 0
        try:
            async with conn.execute(_EXTRACT_RED_SQL) as cursor:
                async for row in cursor:
                    try:
                        raw_tags = row[0] if row[0] else "[]"
                        tags = json.loads(raw_tags)
                        dimension_name: str = row[1] or "UNKNOWN"
                        pattern = f"HIGH_RISK_{dimension_name.upper()}"
                        for tag in tags:
                            await upsert_insight(conn, tag, pattern)
                            updated += 1
                    except Exception:
                        # Per-row error: log and continue — never abort (Req 13.6)
                        logger.exception("Dream Cycle: error processing row, continuing")
        except Exception:
            logger.exception("Dream Cycle: fatal query error")
        return updated
