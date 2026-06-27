"""
web/state.py — AppState: the sole bridge between the API and the UI.

Design rules enforced here:
  1. AppState is the ONLY place that calls the FastAPI backend.
  2. Components receive data exclusively via state vars or computed vars.
  3. No business logic lives in components; all transformations happen here.
  4. Toast notifications are triggered imperatively from event handlers using
     rx.toast.error / rx.toast.warning — no global string state needed.

State hierarchy:
  projects          ← populated by load_projects() on page load
  selected_project  ← populated by select_project(project_id)
  selected_node     ← populated by select_node(node_id)

Selection keys:
  selected_project_id  ← drives sidebar highlight + expansion
  selected_version_id  ← drives version row expansion + node list filter
  selected_node_id     ← drives node row highlight + detail pane render

Computed vars (server-side, cached):
  versions_for_selected_project  ← list[dict] from selected_project["versions"]
  nodes_for_selected_version     ← list[dict] filtered by selected_version_id
  selected_node_name             ← str, safe empty fallback
  selected_node_layer_type       ← str, safe empty fallback
  selected_node_created_at       ← str, safe empty fallback
  selected_node_content_json     ← str, pretty-printed JSON of content_markdown

API URL resolution
──────────────────
All httpx calls originate from the Reflex backend process (server-side), so
the API URL must be reachable from inside the container / Codespace — NOT from
the browser.  "localhost:8000" is correct for server-to-server calls inside a
single container or the same Codespace VM.

Override via CONTEXTA_API_URL if the topology differs (e.g. separate containers
in docker-compose, or external FastAPI deployment).

Codespace auto-detection:
  If CODESPACE_NAME is set, the FastAPI public URL is
  https://{CODESPACE_NAME}-8000.app.github.dev — useful as a fallback, but
  server-to-server should still prefer http://localhost:8000 when both processes
  share the same network namespace.
"""

from __future__ import annotations

import json
import logging
import os

import httpx
import reflex as rx

# ── Logging ───────────────────────────────────────────────────────────────────
# Logs appear in the terminal running "reflex run", not in the browser console.
_log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── API base URL ───────────────────────────────────────────────────────────────
# AppState event handlers call FastAPI server-side via httpx.
# Prefer CONTEXTA_API_URL env var; default to localhost for single-container.
_API_BASE: str = os.environ.get("CONTEXTA_API_URL", "http://localhost:8000")
_HTTP_TIMEOUT: float = 10.0

_log.info("AppState: API base resolved to %s", _API_BASE)


class AppState(rx.State):
    """
    Central application state.

    All fields below are the authoritative UI state.  Event handlers update
    them; components read them.  Nothing else mutates these vars.
    """

    # ── API data ──────────────────────────────────────────────────────────────
    projects: list[dict] = []        # GET /api/projects
    selected_project: dict = {}      # GET /api/projects/{id}
    selected_node: dict = {}         # GET /api/nodes/{id}

    # ── Selection keys ────────────────────────────────────────────────────────
    selected_project_id: str = ""
    selected_version_id: str = ""
    selected_node_id: str = ""

    # ── Loading indicator ─────────────────────────────────────────────────────
    is_loading: bool = False

    # ── Computed vars (cached; auto-deps tracked by Reflex) ───────────────────

    @rx.var(cache=True)
    def versions_for_selected_project(self) -> list[dict]:
        """Versions belonging to the currently expanded project."""
        return self.selected_project.get("versions", [])

    @rx.var(cache=True)
    def nodes_for_selected_version(self) -> list[dict]:
        """Nodes belonging to the currently expanded version."""
        if not self.selected_project or not self.selected_version_id:
            return []
        return [
            n
            for n in self.selected_project.get("nodes", [])
            if n.get("version_id") == self.selected_version_id
        ]

    @rx.var(cache=True)
    def selected_node_name(self) -> str:
        return self.selected_node.get("node_name", "")

    @rx.var(cache=True)
    def selected_node_layer_type(self) -> str:
        return self.selected_node.get("layer_type", "")

    @rx.var(cache=True)
    def selected_node_created_at(self) -> str:
        return self.selected_node.get("created_at", "")

    @rx.var(cache=True)
    def selected_node_content_json(self) -> str:
        """
        Pretty-printed JSON string of the node's content_markdown field.

        content_markdown holds a raw JSON string (the serialised
        ReviewNodePayload).  We parse it here so the detail pane can show
        nicely indented JSON rather than an escaped one-liner.
        Falls back to the raw string when the content is not valid JSON.
        """
        content: str = self.selected_node.get("content_markdown", "")
        if not content:
            return ""
        try:
            parsed = json.loads(content)
            return json.dumps(parsed, indent=2)
        except (json.JSONDecodeError, TypeError):
            return content

    # ── Event handlers ────────────────────────────────────────────────────────

    @rx.event
    def on_mount(self):
        """
        Called via on_load in web.py when the index page is first rendered.
        Chains into load_projects so a single lifecycle hook triggers the
        initial data fetch.
        """
        _log.info("on_mount fired — chaining to load_projects")
        return AppState.load_projects

    async def load_projects(self):
        """
        Fetch all projects from the FastAPI backend.

        Called on page load via app.add_page(on_load=AppState.on_mount).
        All network I/O is server-side; logs appear in the Reflex terminal.
        """
        _log.info(
            "load_projects: starting fetch from %s/api/projects", _API_BASE
        )
        self.is_loading = True
        yield

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.get(f"{_API_BASE}/api/projects")
                resp.raise_for_status()
                self.projects = resp.json()
                _log.info(
                    "load_projects: success — received %d project(s)",
                    len(self.projects),
                )
            except httpx.HTTPStatusError as exc:
                _log.error(
                    "load_projects: HTTP %s from API — %s",
                    exc.response.status_code,
                    exc.response.text,
                )
                error = exc.response.json().get("error", "Failed to load projects.")
                yield rx.toast.error(error)
            except httpx.RequestError as exc:
                _log.error(
                    "load_projects: network error reaching %s — %s",
                    _API_BASE,
                    exc,
                )
                yield rx.toast.error(
                    f"Cannot reach API at {_API_BASE}. Is the server running? ({exc})"
                )

        self.is_loading = False

    async def select_project(self, project_id: str) -> None:
        """
        Expand a project in the sidebar and fetch its versions + nodes.
        Clicking an already-selected project collapses it.
        """
        if project_id == self.selected_project_id:
            # Toggle: collapse
            self.selected_project_id = ""
            self.selected_project = {}
            self.selected_version_id = ""
            self.selected_node_id = ""
            self.selected_node = {}
            return

        self.selected_project_id = project_id
        self.selected_version_id = ""
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
                _log.error(
                    "select_project: HTTP %s — %s",
                    exc.response.status_code,
                    exc.response.text,
                )
                error = exc.response.json().get(
                    "error", f"Failed to load project '{project_id}'."
                )
                yield rx.toast.error(error)
            except httpx.RequestError as exc:
                _log.error("select_project: network error — %s", exc)
                yield rx.toast.error(f"Network error: {exc}")

        self.is_loading = False

    def select_version(self, version_id: str) -> None:
        """
        Expand a version row to reveal its nodes.
        No API call — the nodes are already in selected_project.
        Clicking an already-selected version collapses it.
        """
        if version_id == self.selected_version_id:
            self.selected_version_id = ""
        else:
            self.selected_version_id = version_id

        # Clear node selection when switching versions.
        self.selected_node_id = ""
        self.selected_node = {}

    async def select_node(self, node_id: str) -> None:
        """
        Fetch a node's full detail and display it in the content pane.
        Clicking an already-selected node is a no-op.
        """
        if node_id == self.selected_node_id:
            return

        self.selected_node_id = node_id
        self.is_loading = True
        yield

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            try:
                resp = await client.get(f"{_API_BASE}/api/nodes/{node_id}")
                resp.raise_for_status()
                self.selected_node = resp.json()
            except httpx.HTTPStatusError as exc:
                _log.error(
                    "select_node: HTTP %s — %s",
                    exc.response.status_code,
                    exc.response.text,
                )
                error = exc.response.json().get(
                    "error", f"Failed to load node '{node_id}'."
                )
                yield rx.toast.error(error)
            except httpx.RequestError as exc:
                _log.error("select_node: network error — %s", exc)
                yield rx.toast.error(f"Network error: {exc}")

        self.is_loading = False
