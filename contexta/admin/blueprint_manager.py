"""Prompt Blueprint Manager — Admin Tab CRUD operations.

Wraps the repository-level blueprint functions and enforces the one-active
invariant through the ``activate()`` method (which delegates to the atomic
``activate_blueprint()`` transaction in ``db/repositories.py``).
"""

from __future__ import annotations

from typing import List, Optional

import aiosqlite

from ..db.models import BlueprintRow
from ..db.repositories import (
    activate_blueprint,
    get_active_blueprint,
    list_blueprints,
    save_blueprint_version,
)


class PromptBlueprintManager:
    """CRUD interface for the ``prompt_blueprints`` table.

    Parameters
    ----------
    conn:
        Open database connection held by ``ContextaApp``.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def list_all(self) -> List[BlueprintRow]:
        """Return all blueprint rows ordered by name and version."""
        return await list_blueprints(self._conn)

    async def activate(self, blueprint_id: str) -> None:
        """Atomically activate *blueprint_id* and deactivate all others."""
        await activate_blueprint(self._conn, blueprint_id)

    async def save_new_version(
        self,
        name: str,
        version: str,
        prompt_text: str,
    ) -> BlueprintRow:
        """Create a new blueprint row without modifying existing rows."""
        return await save_blueprint_version(self._conn, name, version, prompt_text)

    async def get_active(self) -> Optional[BlueprintRow]:
        """Return the currently active blueprint, or ``None`` if none is active."""
        return await get_active_blueprint(self._conn)
