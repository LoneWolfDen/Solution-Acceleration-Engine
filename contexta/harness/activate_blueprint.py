"""contexta/harness/activate_blueprint.py — Blueprint activation utility.

Lists all blueprints in the database and activates the first one found.
Useful for resetting blueprint state in local development or after a DB restore.

Usage::

    python -m contexta.harness.activate_blueprint

Set ``CONTEXTA_DB_PATH`` to point at a non-default database location::

    CONTEXTA_DB_PATH=/path/to/db python -m contexta.harness.activate_blueprint
"""

from __future__ import annotations

import asyncio
import os

import aiosqlite

from ..db.repositories import activate_blueprint, list_blueprints

_DB_PATH: str = os.environ.get("CONTEXTA_DB_PATH", "./contexta.db")


async def main() -> None:
    """List blueprints and activate the first one found.

    Exits with a message if the database contains no blueprints.
    Run ``seed_database`` first if the table is empty.
    """
    print(f"[activate] Connecting to database: {_DB_PATH}")
    async with aiosqlite.connect(_DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        blueprints = await list_blueprints(conn)

    if not blueprints:
        print("[activate] No blueprints found. Run 'python -m contexta.harness.seed_database' first.")
        return

    async with aiosqlite.connect(_DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        target = blueprints[0]
        await activate_blueprint(conn, target.id)
        print(
            f"[activate] Activated: '{target.blueprint_name}' "
            f"v{target.version_string} (id={target.id})"
        )
        if len(blueprints) > 1:
            print(f"[activate] {len(blueprints) - 1} other blueprint(s) deactivated.")


if __name__ == "__main__":
    asyncio.run(main())
