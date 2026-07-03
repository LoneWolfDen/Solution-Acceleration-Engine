"""tests/api/test_db_path_consistency.py

Regression test for a bug where review/proposal jobs never left the
"queued" state: ``contexta.api`` (the main FastAPI app / lifespan) and
``contexta.api.pipeline_bridge`` (invoked from a ``BackgroundTasks`` job)
resolved two *different* default database paths when ``CONTEXTA_DB_PATH``
was not set in the environment:

  - ``contexta/api/__init__.py``  ->  "<project_root>/data/contexta.db"
  - ``contexta/api/config.py``    ->  "/data/contexta.db"

Background tasks call ``load_api_config().db_path`` to open their own
connection (see ``contexta/api/pipeline_bridge.py``). If that path differs
from the one the main app used to write the job row, the background task's
``get_review_job()`` / ``get_proposal_job()`` lookup silently returns
``None`` and the job is left in "queued" forever with no LLM calls ever
made and no error surfaced to the user.

This test asserts both paths always agree, independent of environment.
"""

from __future__ import annotations

import importlib


def test_pipeline_bridge_db_path_matches_app_db_path_with_no_env_override(monkeypatch):
    """WebAPIConfig.db_path must equal the path the FastAPI app itself uses
    when CONTEXTA_DB_PATH is not set (the default case for local/dev runs).
    """
    monkeypatch.delenv("CONTEXTA_DB_PATH", raising=False)

    from contexta.api import config as api_config
    importlib.reload(api_config)

    import contexta.api as api_module
    importlib.reload(api_module)

    resolved_by_config = api_config.load_api_config().db_path
    resolved_by_app = api_module._DB_PATH

    assert resolved_by_config == resolved_by_app, (
        "contexta.api._DB_PATH and WebAPIConfig.db_path have diverged — "
        "background pipeline tasks (pipeline_bridge.py) will write/read a "
        "different database file than the main app, causing review and "
        "proposal jobs to stay stuck in 'queued' forever."
    )


def test_pipeline_bridge_db_path_matches_app_db_path_with_env_override(monkeypatch, tmp_path):
    """The two paths must also agree when CONTEXTA_DB_PATH IS set (Docker)."""
    override = str(tmp_path / "contexta.db")
    monkeypatch.setenv("CONTEXTA_DB_PATH", override)

    from contexta.api import config as api_config
    importlib.reload(api_config)

    import contexta.api as api_module
    importlib.reload(api_module)

    assert api_config.load_api_config().db_path == override
    assert api_module._DB_PATH == override
