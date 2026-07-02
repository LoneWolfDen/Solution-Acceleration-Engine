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
import json
import logging
import os

import httpx
import reflex as rx

_log = logging.getLogger(__name__)

_API_BASE: str = os.environ.get("CONTEXTA_API_URL", "http://localhost:8000")
_HTTP_TIMEOUT: float = 15.0


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
    artifact_save_complete: bool = False
    last_saved_artifact: dict = {}
    triage_artifacts: list[dict] = []

    # M3 — Upload File tab
    artifact_upload_filename: str = ""
    _artifact_upload_bytes: bytes = b""

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

    # ── New Project dialog ────────────────────────────────────────────────────
    new_project_name: str = ""
    new_project_dialog_open: bool = False

    # ── Version name input (triage widget) ────────────────────────────────────
    version_name: str = "Version 1"

    # ── Milestone 4: Run Review page ──────────────────────────────────────────
    run_review_version_id: str = ""
    run_review_selected_personas: list[str] = []
    run_review_backend: str = ""
    run_review_context: str = ""
    run_review_is_submitting: bool = False

    # ── Milestone 4: Review status polling ────────────────────────────────────
    active_review_id: str = ""
    active_review_status: str = ""
    active_review_progress_message: str = ""
    review_poll_active: bool = False

    # ── Milestone 4: Proposals ─────────────────────────────────────────────────
    proposals_by_review: dict[str, dict] = {}
    active_proposal_id: str = ""
    active_proposal_status: str = ""
    active_proposal_progress_message: str = ""
    proposal_poll_active: bool = False

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
    @rx.var(cache=True)
    def current_findings(self) -> list[dict]:
        return self.selected_node.get("findings", [])

    @rx.var(cache=True)
    def current_version(self) -> dict:
        """Returns the current version merged with its reviews."""
        if not self.selected_version:
            return {}
        # Ensure selected_version is handled as a dict if necessary
        return {**self.selected_version, "reviews": self.selected_version_reviews}

    @rx.var(cache=True)
    def current_version_artifacts(self) -> list[dict]:
        """Artifact list for the selected version as a typed list[dict].

        Returns list[dict] so rx.foreach receives a typed iterable (not Var[Any]).
        Use artifact["key"].to(list[str]) inside the render fn for nested lists.
        """
        return self.selected_version.get("artifacts", [])

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

    # ── Milestone 4: Run Review computed vars ─────────────────────────────────

    @rx.var(cache=True)
    def run_review_available_backends(self) -> list[str]:
        """Providers with a configured key/URL, sourced from admin config."""
        providers = self.admin_config.get("providers", {})
        return [name for name, status in providers.items() if status == "set"]

    @rx.var(cache=True)
    def run_review_can_submit(self) -> bool:
        return (
            len(self.run_review_selected_personas) > 0
            and self.run_review_version_id != ""
            and not self.run_review_is_submitting
        )

    @rx.var(cache=True)
    def active_review_is_terminal(self) -> bool:
        return self.active_review_status in ("complete", "failed")

    @rx.var(cache=True)
    def current_proposal(self) -> dict:
        """The proposal associated with the currently selected review node, if any."""
        return self.proposals_by_review.get(self.selected_node_id, {})

    @rx.var(cache=True)
    def current_proposal_status(self) -> str:
        return self.current_proposal.get("status", "")

    @rx.var(cache=True)
    def current_proposal_exists(self) -> bool:
        return bool(self.current_proposal)

    @rx.var(cache=True)
    def current_proposal_report(self) -> dict:
        return self.current_proposal.get("report") or {}

    # ── Admin typed accessors ─────────────────────────────────────────────────
    # admin_health and admin_config are plain dict vars, so deep subscript access
    # via Reflex Vars returns Var[Any] — which cannot be further indexed.
    # These computed vars expose each sub-dict with explicit return types so that
    # bracket-indexing in admin.py produces correctly typed Vars.

    @rx.var(cache=True)
    def admin_health_providers(self) -> dict[str, str]:
        return self.admin_health.get("providers", {})

    @rx.var(cache=True)
    def admin_health_last_run(self) -> str:
        return self.admin_health.get("last_run") or ""

    @rx.var(cache=True)
    def admin_config_providers(self) -> dict[str, str]:
        return self.admin_config.get("providers", {})

    @rx.var(cache=True)
    def admin_config_thresholds(self) -> dict[str, float]:
        return self.admin_config.get("thresholds", {})

    @rx.var(cache=True)
    def admin_config_ollama_url_value(self) -> str:
        return str(self.admin_config.get("ollama_url", ""))

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
        await self._reload_selected_project()
        self.is_loading = False

    async def _reload_selected_project(self) -> None:
        """Re-fetch the currently selected project without toggling selection.

        Used after mutations (e.g. version creation) that must refresh the
        project's version/node tree while keeping it expanded in the sidebar.
        Unlike select_project(), this never deselects — it is a pure refresh.
        """
        if not self.selected_project_id:
            return
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.get(
                    f"{_API_BASE}/api/projects/{self.selected_project_id}"
                )
                resp.raise_for_status()
                self.selected_project = resp.json()
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(f"Network error: {exc}", is_error=True)

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
        self.artifact_save_complete = False
        self.artifact_title = ""
        self.artifact_source = "paste"
        self.artifact_content = ""
        self.artifact_url = ""
        self.artifact_tags_applied = []
        self.artifact_tag_suggestions = []
        self.artifact_custom_tag = ""
        self.last_saved_artifact = {}
        self.artifact_upload_filename = ""
        self._artifact_upload_bytes = b""

    def close_ingestion_modal(self):
        self.artifact_ingestion_open = False

    def set_artifact_title(self, title: str):
        self.artifact_title = title

    def set_artifact_source(self, source: str):
        # Map display labels (from rx.radio_group list API) to internal values.
        _display_to_internal = {
            "Paste Text": "paste",
            "URL Reference": "url",
            "Upload File": "upload",
        }
        self.artifact_source = _display_to_internal.get(source, source)

    def set_artifact_content(self, content: str):
        self.artifact_content = content

    def set_artifact_url(self, url: str):
        self.artifact_url = url

    async def handle_artifact_upload(self, files: list[rx.UploadFile]):
        """Read the dropped/selected file into memory for later multipart POST.

        Stores raw bytes in a backend-only var (_artifact_upload_bytes) and
        decodes a UTF-8 preview for tag suggestions.  Auto-fills the title
        field from the filename when the title is still empty.
        """
        if not files:
            return
        file = files[0]
        data = await file.read()
        self._artifact_upload_bytes = data
        self.artifact_upload_filename = file.name or "upload.bin"
        if not self.artifact_title:
            self.artifact_title = self.artifact_upload_filename
        preview = data.decode("utf-8", errors="replace")[:500]
        await self.fetch_tag_suggestions_for(self.artifact_upload_filename, preview)

    def clear_artifact_upload(self):
        self.artifact_upload_filename = ""
        self._artifact_upload_bytes = b""

    def set_artifact_custom_tag(self, tag: str):
        self.artifact_custom_tag = tag

    async def fetch_tag_suggestions(self):
        if not self.artifact_title and not self.artifact_content:
            return
        await self.fetch_tag_suggestions_for(
            self.artifact_title, self.artifact_content[:500]
        )

    async def fetch_tag_suggestions_for(self, filename: str, content_preview: str):
        """Shared suggestion fetch used by both paste/url blur and file upload."""
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.get(
                    f"{_API_BASE}/api/artifacts/suggestions",
                    params={
                        "filename": filename,
                        "content_preview": content_preview,
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
        if self.artifact_source == "upload" and not self._artifact_upload_bytes:
            self.set_toast("Select a file to upload.", is_error=True)
            return
        self.ingestion_is_saving = True
        yield
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                form_data = {
                    "project_id": self.selected_project_id,
                    "title": self.artifact_title,
                    "source": self.artifact_source,
                    "content": self.artifact_content,
                    "url": self.artifact_url,
                    "tags": json.dumps(self.artifact_tags_applied),
                }
                files = None
                if self.artifact_source == "upload":
                    files = {
                        "file": (
                            self.artifact_upload_filename or "upload.bin",
                            self._artifact_upload_bytes,
                            "application/octet-stream",
                        )
                    }
                resp = await client.post(
                    f"{_API_BASE}/api/artifacts",
                    data=form_data,
                    files=files,
                )
                resp.raise_for_status()
                self.last_saved_artifact = resp.json()
                self.artifact_save_complete = True
                self.set_toast(
                    f"Artifact '{self.artifact_title}' saved.", is_error=False)
                self.clear_artifact_upload()
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
                await self._reload_selected_project()
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

    # ── New Project ───────────────────────────────────────────────────────────

    def open_new_project_dialog(self) -> None:
        self.new_project_name = ""
        self.new_project_dialog_open = True

    def set_new_project_name(self, name: str) -> None:
        self.new_project_name = name

    def close_new_project_dialog(self) -> None:
        self.new_project_dialog_open = False
        self.new_project_name = ""

    async def create_project(self) -> None:
        name = self.new_project_name.strip()
        if not name:
            self.set_toast("Project name is required.", is_error=True)
            return
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{_API_BASE}/api/projects",
                    json={"name": name, "global_tags": []},
                )
                resp.raise_for_status()
                data = resp.json()
                self.set_toast(f"Project '{data['name']}' created.", is_error=False)
                self.new_project_dialog_open = False
                self.new_project_name = ""
                p_resp = await client.get(f"{_API_BASE}/api/projects")
                p_resp.raise_for_status()
                raw = p_resp.json().get("projects", [])
                self.projects = [_normalize_project(p) for p in raw]
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(f"Network error: {exc}", is_error=True)

    # ── Version name ──────────────────────────────────────────────────────────

    def set_version_name(self, name: str) -> None:
        self.version_name = name

    # ── Milestone 4: Run Review page ───────────────────────────────────────────

    def init_run_review_page(self) -> None:
        """Reset the Run Review form for a fresh visit to /run-review/{version_id}.

        ``self.version_id`` is auto-injected by Reflex from the dynamic route
        segment ``[version_id]`` (see web/pages/run_review.py) — it is not a
        declared AppState var, but Reflex populates it on every page load.
        """
        self.run_review_version_id = self.version_id
        self.run_review_selected_personas = []
        self.run_review_backend = ""
        self.run_review_context = ""
        self.run_review_is_submitting = False

    def toggle_run_review_persona(self, persona: str) -> None:
        if persona in self.run_review_selected_personas:
            self.run_review_selected_personas = [
                p for p in self.run_review_selected_personas if p != persona
            ]
        else:
            self.run_review_selected_personas = [
                *self.run_review_selected_personas, persona
            ]

    def set_run_review_backend(self, backend: str) -> None:
        self.run_review_backend = backend

    def set_run_review_context(self, context: str) -> None:
        self.run_review_context = context

    async def submit_run_review(self):
        """POST /api/reviews, then redirect to the version page for status polling."""
        if not self.run_review_selected_personas:
            self.set_toast("Select at least one persona role.", is_error=True)
            return
        if not self.run_review_version_id:
            self.set_toast("No version selected.", is_error=True)
            return
        self.run_review_is_submitting = True
        yield
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{_API_BASE}/api/reviews",
                    json={
                        "version_id": self.run_review_version_id,
                        "persona_roles": self.run_review_selected_personas,
                        "context": self.run_review_context,
                        "backend": self.run_review_backend or None,
                    },
                )
                resp.raise_for_status()
                review_id = resp.json().get("review_id", "")
                self.set_toast("Review queued.", is_error=False)
                self.run_review_is_submitting = False
                self.selected_project_id = ""  # force sidebar to re-expand on nav
                yield AppState.start_review_status_poll(review_id, self.run_review_version_id)
                yield rx.redirect("/")
                return
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(f"Network error: {exc}", is_error=True)
        self.run_review_is_submitting = False

    # ── Milestone 4: Review status polling ────────────────────────────────────

    @rx.event(background=True)
    async def start_review_status_poll(self, review_id: str, version_id: str):
        """Poll GET /api/reviews/{review_id}/status every 3s until terminal.

        On completion, reloads the version's review list and the project tree
        so the sidebar/version pane reflect the new review node without a
        manual refresh (Milestone 4.5 / 4.9).
        """
        import asyncio as _asyncio

        async with self:
            self.active_review_id = review_id
            self.active_review_status = "queued"
            self.active_review_progress_message = ""
            self.review_poll_active = True

        terminal = False
        while not terminal:
            await _asyncio.sleep(3)
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                try:
                    resp = await client.get(
                        f"{_API_BASE}/api/reviews/{review_id}/status"
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    async with self:
                        self.active_review_status = "failed"
                        self.active_review_progress_message = f"Polling error: {exc}"
                        self.review_poll_active = False
                    return

            status = data.get("status", "queued")
            async with self:
                self.active_review_status = status
                self.active_review_progress_message = data.get(
                    "progress_message"
                ) or ""

            if status in ("complete", "failed"):
                terminal = True

        async with self:
            self.review_poll_active = False

        if status == "failed":
            async with self:
                self.set_toast(
                    self.active_review_progress_message or "Review failed.",
                    is_error=True,
                )
            return

        # status == "complete" — refresh version reviews + full project tree
        # (Milestone 4.9: the sidebar reads selected_project["nodes"], which
        # only the project-detail endpoint returns — the flat projects[] list
        # only carries aggregate counts).
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                r_resp = await client.get(
                    f"{_API_BASE}/api/versions/{version_id}/reviews"
                )
                r_resp.raise_for_status()
                reviews = r_resp.json().get("reviews", [])
            except Exception:
                reviews = None

            current_project_id = self.selected_project_id
            project_detail = None
            if current_project_id:
                try:
                    p_resp = await client.get(
                        f"{_API_BASE}/api/projects/{current_project_id}"
                    )
                    p_resp.raise_for_status()
                    project_detail = p_resp.json()
                except Exception:
                    project_detail = None

            try:
                pl_resp = await client.get(f"{_API_BASE}/api/projects")
                pl_resp.raise_for_status()
                raw_projects = pl_resp.json().get("projects", [])
            except Exception:
                raw_projects = None

        async with self:
            if reviews is not None and self.selected_version_id == version_id:
                self.selected_version_reviews = reviews
            if project_detail is not None and self.selected_project_id == current_project_id:
                self.selected_project = project_detail
            if raw_projects is not None:
                self.projects = [_normalize_project(p) for p in raw_projects]
            self.set_toast("Review complete.", is_error=False)

    def dismiss_review_status(self) -> None:
        self.active_review_id = ""
        self.active_review_status = ""
        self.active_review_progress_message = ""
        self.review_poll_active = False

    # ── Milestone 4: Proposals ─────────────────────────────────────────────────

    async def generate_proposal(self) -> None:
        """POST /api/proposals for the currently selected review node."""
        review_id = self.selected_node_id
        if not review_id:
            self.set_toast("No review selected.", is_error=True)
            return
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{_API_BASE}/api/proposals",
                    json={"review_id": review_id},
                )
                resp.raise_for_status()
                proposal_id = resp.json().get("proposal_id", "")
                self.proposals_by_review = {
                    **self.proposals_by_review,
                    review_id: {"proposal_id": proposal_id, "status": "queued"},
                }
                self.set_toast("Proposal generation queued.", is_error=False)
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
                return
            except httpx.RequestError as exc:
                self.set_toast(f"Network error: {exc}", is_error=True)
                return
        yield AppState.start_proposal_status_poll(proposal_id, review_id)

    @rx.event(background=True)
    async def start_proposal_status_poll(self, proposal_id: str, review_id: str):
        """Poll GET /api/proposals/{proposal_id}/status every 3s until terminal."""
        import asyncio as _asyncio

        async with self:
            self.active_proposal_id = proposal_id
            self.active_proposal_status = "queued"
            self.active_proposal_progress_message = ""
            self.proposal_poll_active = True

        status = "queued"
        terminal = False
        while not terminal:
            await _asyncio.sleep(3)
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                try:
                    resp = await client.get(
                        f"{_API_BASE}/api/proposals/{proposal_id}/status"
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    async with self:
                        self.active_proposal_status = "failed"
                        self.active_proposal_progress_message = (
                            f"Polling error: {exc}"
                        )
                        self.proposal_poll_active = False
                        self.proposals_by_review = {
                            **self.proposals_by_review,
                            review_id: {
                                "proposal_id": proposal_id, "status": "failed"
                            },
                        }
                    return

            status = data.get("status", "queued")
            async with self:
                self.active_proposal_status = status
                self.active_proposal_progress_message = data.get(
                    "progress_message"
                ) or ""
                self.proposals_by_review = {
                    **self.proposals_by_review,
                    review_id: {
                        "proposal_id": proposal_id,
                        "status": status,
                        "progress_message": data.get("progress_message"),
                        "report": data.get("report") or {},
                    },
                }

            if status in ("complete", "failed"):
                terminal = True

        async with self:
            self.proposal_poll_active = False
            if status == "failed":
                self.set_toast(
                    self.active_proposal_progress_message
                    or "Proposal generation failed.",
                    is_error=True,
                )
            else:
                self.set_toast("Proposal ready.", is_error=False)

    async def refresh_projects(self) -> None:
        """Reload the projects list — used by the sidebar refresh button."""
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.get(f"{_API_BASE}/api/projects")
                resp.raise_for_status()
                raw = resp.json().get("projects", [])
                self.projects = [_normalize_project(p) for p in raw]
            except httpx.HTTPStatusError as exc:
                self.set_toast(self._extract_error(exc), is_error=True)
            except httpx.RequestError as exc:
                self.set_toast(
                    f"Cannot reach API at {_API_BASE}: {exc}", is_error=True
                )

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_error(exc: httpx.HTTPStatusError) -> str:
        try:
            return exc.response.json().get("error", str(exc))
        except Exception:
            return str(exc)
