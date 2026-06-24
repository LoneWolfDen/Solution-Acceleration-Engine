"""KnowledgeMemoryService — persistence layer for arbitration observations.

Each time the ``ArbitratorEngine`` detects a contradiction between two
dimension outputs it calls ``record_observation()`` here, which delegates to
``repositories.record_observation()`` to write a row into the
``knowledge_observations`` SQLite table.

Design contracts
----------------
- This service owns no SQL; all persistence is delegated to the repositories
  layer.
- A ``None`` ``db_conn`` causes ``record_observation()`` to log a warning and
  return ``None`` instead of raising, so callers never need to guard against
  an uninitialised service reference.
- The service is stateless beyond the injected connection — it holds no
  in-memory cache.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import aiosqlite
    from ..db.models import ObservationRow

logger = logging.getLogger(__name__)


class KnowledgeMemoryService:
    """Thin async wrapper that persists arbitration observations to SQLite.

    Parameters
    ----------
    db_conn:
        Open ``aiosqlite.Connection`` held by ``ContextaApp``.  May be
        ``None`` in test environments where no DB is wired.
    """

    def __init__(self, db_conn: Optional["aiosqlite.Connection"]) -> None:
        self._conn = db_conn

    async def record_observation(
        self,
        source: str,
        observation: str,
        dimension_a: Optional[str] = None,
        dimension_b: Optional[str] = None,
    ) -> "Optional[ObservationRow]":
        """Persist one knowledge observation.

        Parameters
        ----------
        source:
            Label identifying where this observation originates, e.g.
            ``"arbitrator"``.
        observation:
            Human-readable description of the detected pattern or conflict.
        dimension_a:
            First ``ReviewDimensionEnum`` value involved, if known.
        dimension_b:
            Second ``ReviewDimensionEnum`` value involved, if known.

        Returns
        -------
        ObservationRow | None
            The persisted row, or ``None`` if no DB connection is available.
        """
        if self._conn is None:
            logger.warning(
                "KnowledgeMemoryService: no DB connection — observation not persisted "
                "(source=%r, observation=%r)",
                source,
                observation,
            )
            return None

        from ..db.repositories import record_observation as _repo_record

        return await _repo_record(
            self._conn,
            source=source,
            observation=observation,
            dimension_a=dimension_a,
            dimension_b=dimension_b,
        )
