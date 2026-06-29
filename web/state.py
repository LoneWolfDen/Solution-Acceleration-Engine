"""
web/state.py — AppState: the sole bridge between the FastAPI backend and the UI.

Design rules:
  1. AppState is the ONLY place that calls the backend API (via httpx).
  2. Components receive data exclusively via state vars or computed vars.
  3. All field-name normalisation (e.g. project_id → id) happens here.
  4. Errors surface as Toast notifications via set_toast(); no silent failures.
  5. Every async handler yields while is_loading=True so the spinner renders.

API URL:
  Handlers run server-side; httpx calls target FastAPI on localhost:8000.
  Override with CONTEXTA_API_URL if topology differs.
"""

from __future__ import annotations
from contexta.api.schemas import FindingItem, VersionDetailResponse
import json
import logging
import os

import httpx
import reflex as rx

_log = logging.getLogger(__name__)

_API_BASE: str = os.environ.get("CONTEXTA_API_URL", "http://localhost:8000")
_HTTP_TIMEOUT: float = 15.0


class ArtifactVar(rx.Base):
    """Typed artifact model for Reflex rx.foreach type inference.

    rx.Base is required (not plain Pydantic BaseModel) so Reflex registers
    every field in its type registry. This lets Reflex resolve ``artifact["tags"]``
    to ``Var[list[str]]`` inside nested rx.foreach calls instead of ``Var[Any]``.
    """

    artifact_id: str = ""
    title: str = ""
    tags: list[str] = []
    is_active: bool = True


def _normalize_project(p: dict) -> dict:
    """Ensure every project dict uses 'id' as the primary key."""
    if "project_id" in p and "id" not in p:
        p = {**p, "id": p["project_id"]}
    return p


class AppState(rx.State):
    """Central application state. Components only read; handlers write."""

    # ── API data ──────────────────────────────────────────────────────────────
    projects: list[dict] = []
    selected_project: dict = {}
    selected_version: dict = {}
    selected_version_reviews: list[dict] = []
    selected_node: dict = {}

    # M3 — Artifact ingestion
    artifact_ingestion_open: bool = False
    artifact_title: str = ""
    artifact_source: str = "paste"
    artifact_content: str = ""
    artifact_url: str = ""
    artifact_tags_applied: list[str] = []
    artifact_tag_suggestions: list[str] = []
    artifact_custom_tag: str = ""
    ingestion_is_saving: bool = False
    last_saved_artifact: dict = {}
    triage_artifacts: list[dict] = []

    # M3 — Admin state (initialised with safe defaults so bracket access is safe)
    admin_config: dict = {
        "providers": {
            "groq": "not_set",
            "openrouter": "not_set",
            "gemini": "not_set",
            "ollama": "not_set",
        },
        "ollama_url": "",
        "thresholds": {"risk": 0.75, "constraint": 0.70, "dependency": 0.80},
        "max_active_projects": 5,
    }
    admin_health: dict = {
        "providers": {
            "groq": "not_set",
            "openrouter": "not_set",
            "gemini": "not_set",
            "ollama": "not_set",
        },
        "last_run": None,
    }
    admin_loading: bool = False
    admin_key_saved_provider: str = ""

    # ── Selection keys ────────────────────────────────────────────────────────
    selected_project_id: str = ""
    selected_version_id: str = ""
    selected_node_id: str = ""

    # ── UI state ──────────────────────────────────────────────────────────────
    is_loading: bool = False
    toast_message: str = ""
    toast_is_error: bool = False

    # ── Computed vars ─────────────────────────────────────────────────────────

    @rx.var(cache=True)
    def active_view(self) -> str:
        if self.selected_node_id and self.selected_node:
            return "node"
        if self.selected_version_id:
            return "version"
        return "welcome"

    @rx.var(cache=True)
    def current_node(self) -> dict:
        return self.selected_node
    """
    @rx.var(cache=True)
    def current_findings(self) -> list:
        return self.selected_node.get("findings", [])
    """
    @rx.var(cache=True)
    def current_findings(self) -> list[FindingItem]:
        # If the API returns a list of raw dicts, convert them:
        raw_data = self.selected_node.get("findings", [])
        return [FindingItem(**item) for item in raw_data]

    @rx.var(cache=True)
    def current_version(self) -> dict:
        """Returns the current version merged with its reviews."""
        if not self.selected_version:
            return {}
        # Ensure selected_version is handled as a dict if necessary
        return {**self.selected_version, "reviews": self.selected_version_reviews}

    @rx.var(cache=True)
    def current_version_artifacts(self) -> list[ArtifactVar]:
        """Typed artifact list for the selected version.

        Returns ``list[ArtifactVar]`` so Reflex can infer field types inside
        ``rx.foreach``, including the nested ``artifact["tags"]`` list.
        Returns an empty list when no version is selected.
        """
        raw = self.selected_version.get("artifacts", [])
        return [
            ArtifactVar(
                artifact_id=a.get("artifact_id", ""),
                title=a.get("title", ""),
                tags=a.get("tags", []),
                is_active=a.get("is_active", True),
            )
            for a in raw
        ]

    @rx.var(cache=True)
    def triage_artifacts_typed(self) -> list[ArtifactVar]:
        """Typed triage artifact list for rx.foreach compatibility.

        Wraps ``triage_artifacts: list[dict]`` so Reflex can resolve
        ``artifact["tags"]`` to ``Var[list[str]]`` in the triage widget.
        """
        return [
            ArtifactVar(
                artifact_id=a.get("artifact_id", ""),
                title=a.get("title", ""),
                tags=a.get("tags", []),
                is_active=a.get("is_active", True),
            )
            for a in self.triage_artifacts
        ]

    @rx.var(cache=True)
    def versions_for_selected_project(self) -> list[dict]:
        return self.selected_project.get("versions", [])

    @rx.var(cache=True)
    def nodes_for_selected_version(self) -> list[dict]:
        if not self.selected_project or not self.selected_version_id:
            return []
        return [
            n
            for n in self.selected_project.get("nodes", [])
            if n.get("version_id") == self.selected_version_id
        ]

    @rx.var(cache=True)
    def selected_node_name(self) -> str:
        return self.selected_node.get("review_id", "")[:8] or ""

    @rx.var(cache=True)
    def selected_node_status(self) -> str:
        return self.selected_node.get("status", "")

    @rx.var(cache=True)
    def selected_node_persona(self) -> str:
        return self.selected_node.get("persona", "")

    @rx.var(cache=True)
    def finding_counts(self) -> dict:
        s = self.selected_node.get("summary") or {}
        return {
            "risks": s.get("risks", 0),
            "constraints": s.get("constraints", 0),
            "dependencies": s.get("dependencies", 0),
            "assumptions": s.get("assumptions", 0),
            "action_items": s.get("action_items", 0),
        }

    @rx.var(cache=True)
    def triage_active_artifact_ids(self) -> list[str]:
        return [a["artifact_id"] for a in self.triage_artifacts if a.get("is_active")]

    @rx.var(cache=True)
    def can_create_version(self) -> bool:
        return len(self.triage_active_artifact_ids) > 0 and self.selected_project_id != ""

    # ── Toast helpers ─────────────────────────────────────────────────────────

    def set_toast(self, message: str, is_error: bool = False) -> None:
        self.toast_message = message
        self.toast_is_error = is_error

    def clear_toast(self) -> None:
        self.toast_message = ""
        self.toast_is_error = False

    # ── Page load ─────────────────────────────────────────────────────────────

    async def load_projects(self):
        """Fetch all projects on page load."""
        self.is_loading = True
        yield
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.get(f"{_API_BASE}/api/projects")
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("projects", data) if isinstance(
                    data, dict) else data
                self.projects = [_normalize_project(p) for p in raw]
                _log.info("load_projects: loaded %d project(s)",
                          len(self.projects))
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(
                    f"Cannot reach API at {_API_BASE}: {exc}", is_error=True)
        self.is_loading = False

    # ── Project selection ─────────────────────────────────────────────────────

    async def select_project(self, project_id: str):
        if project_id == self.selected_project_id:
            self.selected_project_id = ""
            self.selected_project = {}
            self.selected_version_id = ""
            self.selected_version = {}
            self.selected_version_reviews = []
            self.selected_node_id = ""
            self.selected_node = {}
            return
        self.selected_project_id = project_id
        self.selected_version_id = ""
        self.selected_version = {}
        self.selected_version_reviews = []
        self.selected_node_id = ""
        self.selected_node = {}
        self.is_loading = True
        yield
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.get(f"{_API_BASE}/api/projects/{project_id}")
                resp.raise_for_status()
                self.selected_project = resp.json()
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(f"Network error: {exc}", is_error=True)
        self.is_loading = False

    # ── Version selection ─────────────────────────────────────────────────────

    async def select_version(self, version_id: str):
        if version_id == self.selected_version_id:
            self.selected_version_id = ""
            self.selected_version = {}
            self.selected_version_reviews = []
            self.selected_node_id = ""
            self.selected_node = {}
            return
        self.selected_version_id = version_id
        self.selected_node_id = ""
        self.selected_node = {}
        self.is_loading = True
        yield
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                v_resp = await client.get(f"{_API_BASE}/api/versions/{version_id}")
                v_resp.raise_for_status()
                version_data = v_resp.json()
                if "version_id" in version_data and "id" not in version_data:
                    version_data["id"] = version_data["version_id"]
                self.selected_version = version_data

                r_resp = await client.get(f"{_API_BASE}/api/versions/{version_id}/reviews")
                r_resp.raise_for_status()
                self.selected_version_reviews = r_resp.json().get("reviews", [])
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(f"Network error: {exc}", is_error=True)
        self.is_loading = False

    # ── Node selection ────────────────────────────────────────────────────────

    async def select_node(self, node_id: str):
        if node_id == self.selected_node_id:
            return
        self.selected_node_id = node_id
        self.selected_node = {}
        self.is_loading = True
        yield
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.get(f"{_API_BASE}/api/nodes/{node_id}")
                resp.raise_for_status()
                self.selected_node = resp.json()
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(f"Network error: {exc}", is_error=True)
        self.is_loading = False

    # ── Milestone 3: Artifact ingestion ───────────────────────────────────────

    def open_ingestion_modal(self):
        self.artifact_ingestion_open = True
        self.artifact_title = ""
        self.artifact_source = "paste"
        self.artifact_content = ""
        self.artifact_url = ""
        self.artifact_tags_applied = []
        self.artifact_tag_suggestions = []
        self.artifact_custom_tag = ""
        self.last_saved_artifact = {}

    def close_ingestion_modal(self):
        self.artifact_ingestion_open = False

    def set_artifact_title(self, title: str):
        self.artifact_title = title

    def set_artifact_source(self, source: str):
        self.artifact_source = source

    def set_artifact_content(self, content: str):
        self.artifact_content = content

    def set_artifact_url(self, url: str):
        self.artifact_url = url

    def set_artifact_custom_tag(self, tag: str):
        self.artifact_custom_tag = tag

    async def fetch_tag_suggestions(self):
        if not self.artifact_title and not self.artifact_content:
            return
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.get(
                    f"{_API_BASE}/api/artifacts/suggestions",
                    params={
                        "filename": self.artifact_title,
                        "content_preview": self.artifact_content[:500],
                    },
                )
                resp.raise_for_status()
                self.artifact_tag_suggestions = [
                    s for s in resp.json().get("suggestions", [])
                    if s not in self.artifact_tags_applied
                ]
            except Exception as exc:
                _log.warning("Tag suggestions failed: %s", exc)

    def toggle_suggestion_tag(self, tag: str):
        if tag in self.artifact_tags_applied:
            self.artifact_tags_applied = [
                t for t in self.artifact_tags_applied if t != tag]
        else:
            self.artifact_tags_applied = [*self.artifact_tags_applied, tag]

    def add_custom_tag(self):
        tag = self.artifact_custom_tag.strip()
        if tag and tag not in self.artifact_tags_applied:
            self.artifact_tags_applied = [*self.artifact_tags_applied, tag]
        self.artifact_custom_tag = ""

    def handle_tag_key_down(self, key: str):
        """Called from on_key_down on the tag input; adds tag on Enter."""
        if key == "Enter":
            self.add_custom_tag()

    def remove_applied_tag(self, tag: str):
        self.artifact_tags_applied = [
            t for t in self.artifact_tags_applied if t != tag]

    async def save_artifact(self):
        if not self.artifact_title or not self.selected_project_id:
            self.set_toast("Title and project are required.", is_error=True)
            return
        self.ingestion_is_saving = True
        yield
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{_API_BASE}/api/artifacts",
                    data={
                        "project_id": self.selected_project_id,
                        "title": self.artifact_title,
                        "source": self.artifact_source,
                        "content": self.artifact_content,
                        "url": self.artifact_url,
                        "tags": json.dumps(self.artifact_tags_applied),
                    },
                )
                resp.raise_for_status()
                self.last_saved_artifact = resp.json()
                self.set_toast(
                    f"Artifact '{self.artifact_title}' saved.", is_error=False)
                await self._load_triage_artifacts()
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(f"Network error: {exc}", is_error=True)
        self.ingestion_is_saving = False

    async def _load_triage_artifacts(self):
        if not self.selected_project_id:
            return
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.get(
                    f"{_API_BASE}/api/projects/{self.selected_project_id}/artifacts"
                )
                resp.raise_for_status()
                self.triage_artifacts = resp.json().get("artifacts", [])
            except Exception as exc:
                _log.warning("Failed to load triage artifacts: %s", exc)

    async def load_triage_artifacts(self):
        await self._load_triage_artifacts()

    async def toggle_artifact_active(self, artifact_id: str):
        """PATCH /api/artifacts/{id} — optimistic toggle with rollback on error."""
        # Determine target state before mutating
        new_active = True
        for a in self.triage_artifacts:
            if a.get("artifact_id") == artifact_id:
                new_active = not a.get("is_active", True)
                break

        # Optimistic update
        self.triage_artifacts = [
            {**a, "is_active": new_active} if a.get(
                "artifact_id") == artifact_id else a
            for a in self.triage_artifacts
        ]
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.patch(
                    f"{_API_BASE}/api/artifacts/{artifact_id}",
                    json={"active": new_active},
                )
                resp.raise_for_status()
            except Exception as exc:
                # Revert optimistic update
                self.triage_artifacts = [
                    {**a, "is_active": not new_active}
                    if a.get("artifact_id") == artifact_id
                    else a
                    for a in self.triage_artifacts
                ]
                self.set_toast(f"Toggle failed: {exc}", is_error=True)

    async def create_version_from_triage(self, version_name: str):
        active_ids = self.triage_active_artifact_ids
        if not active_ids:
            self.set_toast("Select at least one artifact.", is_error=True)
            return
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{_API_BASE}/api/versions",
                    json={
                        "project_id": self.selected_project_id,
                        "version_name": version_name or "Version 1",
                        "artifact_ids": active_ids,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                self.set_toast(
                    f"Version '{data.get('name', '')}' created.", is_error=False)
                self.artifact_ingestion_open = False
                await self.select_project(self.selected_project_id)
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(f"Network error: {exc}", is_error=True)

    # ── Milestone 3: Admin ────────────────────────────────────────────────────

    async def load_admin_page(self):
        self.admin_loading = True
        yield
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                h_resp = await client.get(f"{_API_BASE}/api/admin/health")
                h_resp.raise_for_status()
                self.admin_health = h_resp.json()

                c_resp = await client.get(f"{_API_BASE}/api/admin/config")
                c_resp.raise_for_status()
                self.admin_config = c_resp.json()
            except Exception as exc:
                _log.error("load_admin_page error: %s", exc)
                self.set_toast(
                    f"Failed to load admin data: {exc}", is_error=True)
        await self._load_projects_for_admin()
        self.admin_loading = False

    async def _load_projects_for_admin(self):
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.get(f"{_API_BASE}/api/projects")
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("projects", data) if isinstance(
                    data, dict) else data
                self.projects = [_normalize_project(p) for p in raw]
            except Exception as exc:
                _log.warning("Admin: failed to load projects: %s", exc)

    async def save_api_key(self, provider: str, key: str):
        """POST /api/admin/config to save an API key or Ollama URL."""
        if not key or not str(key).strip():
            self.set_toast("Value must not be empty.", is_error=True)
            return
        # Distinguish between LLM keys and Ollama URL
        if provider == "ollama":
            payload: dict = {"field": "ollama_url",
                             "ollama_url": str(key).strip()}
        else:
            payload = {"field": "api_key",
                       "provider": provider, "key": str(key).strip()}

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.post(f"{_API_BASE}/api/admin/config", json=payload)
                resp.raise_for_status()
                self.admin_key_saved_provider = provider
                self.set_toast(
                    f"{provider.upper()} key saved.", is_error=False)
                c_resp = await client.get(f"{_API_BASE}/api/admin/config")
                c_resp.raise_for_status()
                self.admin_config = c_resp.json()
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(f"Network error: {exc}", is_error=True)

    async def save_threshold(self, name: str, value: float):
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{_API_BASE}/api/admin/config",
                    json={"field": "threshold", "threshold_name": name,
                          "threshold_value": value},
                )
                resp.raise_for_status()
                self.set_toast(f"Threshold '{name}' saved.", is_error=False)
                c_resp = await client.get(f"{_API_BASE}/api/admin/config")
                c_resp.raise_for_status()
                self.admin_config = c_resp.json()
            except Exception as exc:
                self.set_toast(f"Save failed: {exc}", is_error=True)

    async def delete_project(self, project_id: str):
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.delete(f"{_API_BASE}/api/projects/{project_id}")
                resp.raise_for_status()
                self.set_toast("Project deleted.", is_error=False)
                await self._load_projects_for_admin()
                if self.selected_project_id == project_id:
                    self.selected_project_id = ""
                    self.selected_project = {}
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(f"Network error: {exc}", is_error=True)

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_error(exc: httpx.HTTPStatusError) -> str:
        try:
            return exc.response.json().get("error", str(exc))
        except Exception:
            return str(exc)
