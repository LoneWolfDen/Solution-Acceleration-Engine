"""KnowledgeMemory — context dataclass and service layer.

KnowledgeContext
    Lightweight query descriptor passed into pipeline components to identify
    which observations are relevant before an LLM call.

KnowledgeMemoryService
    Thin async service that wraps the DB repository functions.  Injected into
    DimensionRunner, ArbitratorEngine, LayerTwoArbitrator, and ProactiveAdvisor
    so they can query prior interventions and record new ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import aiosqlite

from ..db.repositories import get_observations_for_context, write_observation
from ..db.models import ObservationRow
from ..models.enums import PhaseEnum


@dataclass
class KnowledgeContext:
    """Describes the current pipeline position for observation lookup.

    Attributes
    ----------
    phase:
        Which pipeline phase is executing (DIMENSION_REVIEW, ARBITRATION, …).
    node_id:
        The exploration node id or a session-level context key.  Used for
        audit trails; observations are retrieved cross-node by dimension to
        enable cross-project learning.
    dimension:
        Optional dimension name (ReviewDimensionEnum.value).  When provided,
        only observations for this dimension are returned.
    """

    phase: PhaseEnum
    node_id: str
    dimension: Optional[str] = field(default=None)


class KnowledgeMemoryService:
    """Async service that reads and writes KnowledgeMemory observations.

    Injected as an optional dependency into pipeline components.  All callers
    treat it as optional — a ``None`` service means no prior context is
    available and prompts are built without Contextual Constraints.

    Parameters
    ----------
    conn:
        Open aiosqlite connection shared with the rest of the application.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def get_observations(
        self,
        context: KnowledgeContext,
        limit: int = 10,
    ) -> List[ObservationRow]:
        """Return observations matching the given context.

        Queries by dimension (if set in context) and phase.  Results are
        ordered newest-first and capped at *limit* to avoid bloating prompts.

        Parameters
        ----------
        context:
            KnowledgeContext describing the current pipeline position.
        limit:
            Maximum number of observations to return.

        Returns
        -------
        List[ObservationRow]
            Matching observations; empty list if none found.
        """
        return await get_observations_for_context(
            self._conn,
            dimension=context.dimension,
            phase=context.phase.value,
            limit=limit,
        )

    async def record_observation(
        self,
        phase: PhaseEnum,
        node_id: str,
        dimension: str,
        base_value: str,
        amended_value: str,
        rationale: str,
    ) -> ObservationRow:
        """Persist a new user annotation as a KnowledgeMemory observation.

        Called by the TUI annotation handler after a user confirms an edit.
        The persisted row is returned immediately so callers can log or
        surface it in the UI without a separate read.

        Parameters
        ----------
        phase:         PhaseEnum value for the originating pipeline phase.
        node_id:       Exploration node id or session context key.
        dimension:     ReviewDimensionEnum.value of the annotated finding.
        base_value:    Original AI-produced summary text.
        amended_value: User's override text.
        rationale:     Why the user made this change.

        Returns
        -------
        ObservationRow
            The newly persisted observation.
        """
        return await write_observation(
            self._conn,
            phase=phase.value,
            node_id=node_id,
            dimension=dimension,
            base_value=base_value,
            amended_value=amended_value,
            rationale=rationale,
        )
