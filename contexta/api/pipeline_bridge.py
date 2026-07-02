"""
contexta/api/pipeline_bridge.py — Wires the Web API background tasks to the
real contexta.pipeline engine (Milestone 4).

Replaces the Milestone 1 stubs in routers/reviews.py and routers/proposals.py.
Both background tasks share the same LLM resolution and blueprint lookup
logic, so it lives here once instead of being duplicated per-router.

Design notes
------------
- Each task opens its own ``aiosqlite`` connection via ``init_database()``
  (mirrors the pattern already used by the Milestone 1 stubs) because
  ``BackgroundTasks`` run after the request's own connection may have been
  torn down by FastAPI's dependency-injection cleanup.
- LLM credentials are read from the ``app_config`` table (set via the Admin
  Dashboard) rather than from environment variables — the Web UI is designed
  to run without ``CONTEXTA_LLM_BACKEND`` set at container start.
- If no provider is configured, or no active blueprint exists, the task
  fails the job with a clear ``progress_message`` instead of raising an
  unhandled exception in the background task (FastAPI logs but does not
  surface those to the client).
"""

from __future__ import annotations

import logging
from typing import List, Optional

import aiosqlite

from ..db.schema import init_database
from ..llm.provider import LLMConfig
from ..mcp.artifact_registry import ArtifactRegistry, IngestedArtifact
from ..models.payloads import ReviewNodePayload
from . import repositories as api_repo
from .config_keys import KEY_GEMINI, KEY_GROQ, KEY_OLLAMA_URL, KEY_OPENROUTER

logger = logging.getLogger(__name__)


class PipelineBridgeError(Exception):
    """Raised when the pipeline cannot be started (bad config, no blueprint)."""


# ── LLM resolution ────────────────────────────────────────────────────────────

# Maps an app_config provider key to a LiteLLM model identifier.  These are
# the smallest/cheapest instruction-tuned models per provider, matching the
# offline-first / open-source-only constraint: no cost assumptions are made
# beyond "works out of the box with a bare API key".
_PROVIDER_TO_MODEL: dict[str, str] = {
    KEY_GROQ: "groq/llama-3.1-8b-instant",
    KEY_OPENROUTER: "openrouter/meta-llama/llama-3.1-8b-instruct",
    KEY_GEMINI: "gemini/gemini-1.5-flash",
}

# Preference order when the caller does not request a specific backend.
_PROVIDER_PRIORITY: List[str] = [KEY_GROQ, KEY_OPENROUTER, KEY_GEMINI, KEY_OLLAMA_URL]


async def resolve_llm_config(
    conn: aiosqlite.Connection, requested_backend: str = ""
) -> LLMConfig:
    """Build an ``LLMConfig`` from the ``app_config`` table.

    Parameters
    ----------
    conn:
        Open aiosqlite connection.
    requested_backend:
        Provider name as surfaced in ``AdminConfigResponse.providers``
        (``"groq" | "openrouter" | "gemini" | "ollama"``).  Empty string
        means "pick the first configured provider" in priority order.

    Raises
    ------
    PipelineBridgeError
        If no provider is configured, or the requested provider has no
        stored credential.
    """
    config = await api_repo.get_all_config(conn)

    candidates = (
        [_backend_key(requested_backend)] if requested_backend else _PROVIDER_PRIORITY
    )

    for key in candidates:
        value = config.get(key)
        if not value:
            continue
        if key == KEY_OLLAMA_URL:
            return LLMConfig(model="ollama/llama3", base_url=value)
        model = _PROVIDER_TO_MODEL.get(key)
        if model is None:
            continue
        return LLMConfig(model=model, api_key=value)

    raise PipelineBridgeError(
        "No LLM provider is configured. Add an API key or Ollama URL on the "
        "Admin page before running a review."
    )


def _backend_key(provider_name: str) -> str:
    mapping = {
        "groq": KEY_GROQ,
        "openrouter": KEY_OPENROUTER,
        "gemini": KEY_GEMINI,
        "ollama": KEY_OLLAMA_URL,
    }
    key = mapping.get(provider_name.lower())
    if key is None:
        raise PipelineBridgeError(f"Unknown AI backend '{provider_name}'.")
    return key


# ── Artifact loading ──────────────────────────────────────────────────────────


async def build_artifact_registry(
    conn: aiosqlite.Connection, version_id: str
) -> ArtifactRegistry:
    """Load all *active* artifacts linked to a version into an ArtifactRegistry.

    Raises
    ------
    PipelineBridgeError
        If the version has zero active linked artifacts — the pipeline
        cannot run without source material.
    """
    from ..api import repositories as _api_repo  # local alias, avoids shadowing

    all_artifacts = await _api_repo.list_artifacts_for_version(conn, version_id)
    active = [a for a in all_artifacts if a.is_active]
    if not active:
        raise PipelineBridgeError(
            "This version has no active artifacts. Toggle at least one "
            "artifact on before running a review."
        )

    registry = ArtifactRegistry()
    for artifact in active:
        registry.register(
            IngestedArtifact(
                uri=f"artifact://{artifact.id}",
                file_path=artifact.filename or artifact.title,
                content=artifact.content,
                line_count=len(artifact.content.splitlines()),
            )
        )
    return registry


# ── Blueprint resolution ──────────────────────────────────────────────────────

_DEFAULT_BLUEPRINT_NAME = "Default Web Review Blueprint"
_DEFAULT_BLUEPRINT_PROMPT = (
    "You are a senior technical delivery reviewer. Review the provided "
    "solution artifacts with rigorous scrutiny, focusing on delivery risk, "
    "technical feasibility, and commercial viability. Ground every finding "
    "in the supplied source material."
)


async def get_or_create_active_blueprint(conn: aiosqlite.Connection):
    """Return the active ``BlueprintRow``, seeding a default one if none exists.

    The TUI workflow requires an operator to explicitly activate a blueprint
    via the Admin Tab.  The Web UI has no equivalent step yet, so a sensible
    default is created and activated on first use rather than failing every
    review with "no active blueprint".
    """
    from ..db.repositories import (
        activate_blueprint,
        get_active_blueprint,
        save_blueprint_version,
    )

    existing = await get_active_blueprint(conn)
    if existing is not None:
        return existing

    created = await save_blueprint_version(
        conn,
        name=_DEFAULT_BLUEPRINT_NAME,
        version="1.0.0",
        prompt_text=_DEFAULT_BLUEPRINT_PROMPT,
    )
    await activate_blueprint(conn, created.id)
    logger.info("Seeded and activated default blueprint '%s'.", created.blueprint_name)
    return created


# ── Review pipeline task (Milestone 4.3) ──────────────────────────────────────


async def run_review_pipeline_task(
    review_id: str, db_path: str, backend: Optional[str] = None
) -> None:
    """Background task: run the real 12-dimension Layer 1 pipeline.

    Loads the review job, resolves LLM config + blueprint + artifacts, runs
    all 12 dimensions via ``TaskOrchestrator``, and commits a single
    exploration node on success.  Updates ``review_jobs.status`` throughout
    so the UI's polling loop (``GET /api/reviews/{id}/status``) reflects
    real progress.
    """
    from ..llm.prompts import PromptBuilder
    from ..pipeline.dimension_runner import TaskOrchestrator, make_dimension_runner

    conn = await init_database(db_path)
    try:
        job = await api_repo.get_review_job(conn, review_id)
        if job is None:
            logger.error("run_review_pipeline_task: review job %s not found.", review_id)
            return

        await api_repo.update_review_job_status(
            conn, review_id, "running", progress_message="Preparing review…"
        )

        from ..db import repositories as db_repo

        version = await db_repo.get_version(conn, job.version_id)
        if version is None:
            await api_repo.update_review_job_status(
                conn, review_id, "failed",
                progress_message=f"Version '{job.version_id}' no longer exists.",
            )
            return

        try:
            llm_config = await resolve_llm_config(conn, backend or "")
            registry = await build_artifact_registry(conn, job.version_id)
            blueprint = await get_or_create_active_blueprint(conn)
        except PipelineBridgeError as exc:
            await api_repo.update_review_job_status(
                conn, review_id, "failed", progress_message=str(exc)
            )
            return

        builder = PromptBuilder(
            blueprint=blueprint,
            schema_json=ReviewNodePayload.model_json_schema().__str__(),
        )

        async def _on_state_change(task) -> None:
            await api_repo.update_review_job_status(
                conn, review_id, "running",
                progress_message=f"{task.dimension.value}: {task.state.value}",
            )

        runner_fn = make_dimension_runner(
            config=llm_config, builder=builder, registry=registry
        )
        orchestrator = TaskOrchestrator(
            on_state_change=_on_state_change, runner_fn=runner_fn
        )

        await orchestrator.launch_all()

        if not orchestrator.all_complete():
            incomplete = [d.value for d in orchestrator.incomplete_dimensions()]
            await api_repo.update_review_job_status(
                conn, review_id, "failed",
                progress_message=f"Dimensions failed: {', '.join(incomplete)}",
            )
            return

        from ..pipeline.dimension_runner import commit_exploration_node

        persona_label = job.persona_roles[0] if job.persona_roles else "Reviewer"
        node = await commit_exploration_node(
            orchestrator,
            conn,
            project_id=version.project_id,
            node_name=f"{persona_label} Review — {version.name}",
        )
        await conn.execute(
            "UPDATE nodes SET version_id = ? WHERE id = ?", (job.version_id, node.id)
        )
        await conn.commit()

        await api_repo.update_review_job_status(
            conn, review_id, "complete",
            progress_message="Review complete.", node_id=node.id,
        )
        logger.info("Review %s completed — node %s written.", review_id, node.id)
    except Exception as exc:  # noqa: BLE001 — background task: must not raise
        logger.exception("run_review_pipeline_task failed for review %s", review_id)
        try:
            await api_repo.update_review_job_status(
                conn, review_id, "failed", progress_message=f"Unexpected error: {exc}"
            )
        except Exception:
            logger.exception("Failed to record failure status for review %s", review_id)
    finally:
        await conn.close()


# ── Proposal synthesis task (Milestone 4.8) ───────────────────────────────────


class _LLMConfigAdapter:
    """Minimal duck-typed stand-in for ``ContextaConfig``.

    ``LayerTwoArbitrator.__init__`` only reads ``llm_backend``, ``llm_api_key``,
    and ``llm_base_url`` off the config object it receives — it does not
    require the full ``pydantic-settings``-backed ``ContextaConfig`` (which
    mandates ``CONTEXTA_LLM_BACKEND`` be set as an environment variable, an
    assumption that does not hold for the Web UI's DB-stored credentials).
    """

    def __init__(self, llm_config: LLMConfig) -> None:
        self.llm_backend = llm_config.model
        self.llm_api_key = llm_config.api_key
        self.llm_base_url = llm_config.base_url


async def run_proposal_pipeline_task(proposal_id: str, db_path: str) -> None:
    """Background task: run the real Layer 2 synthesis pipeline.

    Loads the Layer 1 exploration node produced by the linked review job,
    reconstructs all 12 ``ReviewNodePayload`` objects, collects their
    ``IssueFinding`` objects, and runs ``LayerTwoArbitrator.synthesize()``
    to produce a ``ReconciliationReport``.  The report is persisted as a
    synthesis node (child of the exploration node) via ``write_synthesis_node``.
    """
    from ..db import repositories as db_repo
    from ..pipeline.arbitrator import LayerTwoArbitrator, LayerTwoArbitratorError

    conn = await init_database(db_path)
    try:
        job = await api_repo.get_proposal_job(conn, proposal_id)
        if job is None:
            logger.error("run_proposal_pipeline_task: proposal job %s not found.", proposal_id)
            return

        await api_repo.update_proposal_job_status(
            conn, proposal_id, "running", progress_message="Preparing synthesis…"
        )

        review_job = await api_repo.get_review_job(conn, job.review_job_id)
        if review_job is None or not review_job.node_id:
            await api_repo.update_proposal_job_status(
                conn, proposal_id, "failed",
                progress_message="Source review has no completed exploration node.",
            )
            return

        exploration_node = await db_repo.get_node(conn, review_job.node_id)
        if exploration_node is None:
            await api_repo.update_proposal_job_status(
                conn, proposal_id, "failed",
                progress_message=f"Exploration node '{review_job.node_id}' not found.",
            )
            return

        try:
            payloads = _load_dimension_payloads(exploration_node)
            llm_config = await resolve_llm_config(conn)
        except PipelineBridgeError as exc:
            await api_repo.update_proposal_job_status(
                conn, proposal_id, "failed", progress_message=str(exc)
            )
            return

        findings = [f for payload in payloads for f in payload.findings]

        engine = LayerTwoArbitrator(config=_LLMConfigAdapter(llm_config))
        try:
            report = await engine.synthesize(findings)
        except LayerTwoArbitratorError as exc:
            await api_repo.update_proposal_job_status(
                conn, proposal_id, "failed", progress_message=str(exc)
            )
            return

        synthesis_node = await db_repo.write_synthesis_node(
            conn,
            project_id=exploration_node.project_id,
            parent_id=exploration_node.id,
            node_name=f"Proposal Synthesis — {exploration_node.node_name}",
            report=report,
            version_id=exploration_node.version_id,
        )

        await api_repo.update_proposal_job_status(
            conn, proposal_id, "complete",
            progress_message="Proposal ready.", node_id=synthesis_node.id,
        )
        logger.info(
            "Proposal %s completed — synthesis node %s written.",
            proposal_id, synthesis_node.id,
        )
    except Exception as exc:  # noqa: BLE001 — background task: must not raise
        logger.exception("run_proposal_pipeline_task failed for proposal %s", proposal_id)
        try:
            await api_repo.update_proposal_job_status(
                conn, proposal_id, "failed", progress_message=f"Unexpected error: {exc}"
            )
        except Exception:
            logger.exception("Failed to record failure status for proposal %s", proposal_id)
    finally:
        await conn.close()


def _load_dimension_payloads(exploration_node) -> List[ReviewNodePayload]:
    """Reconstruct all 12 ``ReviewNodePayload`` objects from a NodeRow.

    Raises
    ------
    PipelineBridgeError
        If ``metadata_json['dimensions']`` is missing or empty — this
        indicates the node was not written by ``commit_exploration_node()``.
    """
    import json as _json

    raw_metadata = exploration_node.metadata_json
    metadata = (
        _json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
    )
    dimension_dicts = metadata.get("dimensions") or []
    if not dimension_dicts:
        raise PipelineBridgeError(
            "The source review node has no stored dimension payloads."
        )
    return [ReviewNodePayload.model_validate(d) for d in dimension_dicts]
