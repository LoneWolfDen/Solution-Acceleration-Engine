# Contexta Implementation Gap Analysis

## (a) TL;DR — Originally Reported Issues

**Review Linking:** `Implemented_Not_Wired`. The backend (`review_links` table, `insert_review_links`/`get_linked_review_ids`/`list_linkable_reviews` in `contexta/api/repositories.py`) and API (`POST /api/reviews` accepting `linked_review_ids`, `GET /api/versions/{version_id}/reviews/linkable`) are fully built and correctly wired into the FastAPI app. However, the web UI for selecting linked reviews is explicitly disabled in `web/pages/run_review.py` (a comment reads "TEMPORARILY DISABLED - Reflex list[dict] typing issue"), and the fully-built `web/components/review_link_selector.py` component has zero call sites anywhere in `web/`. A separate, related sub-feature — Prior Review Intelligence injection via `_build_prior_intelligence()` in `contexta/api/pipeline_bridge.py` — does work end-to-end and is not part of this gap. See full finding under [Review Linking & Prior Intelligence](#review-linking--prior-intelligence) in section (c).

**Project-Scoped Proposals:** `Implemented_Differently`. The backend/API (`contexta/api/routers/proposals.py`, `list_proposals_for_version` in `contexta/api/repositories.py`) implement proposal listing strictly scoped to a single version (enforced via an active `WHERE rj.version_id = ?` filter with a 422 guard), whereas the originally reported expectation was project-wide proposal aggregation. This is a scope divergence from the user's expectation, not from a written spec document. The UI is also unwired on top of this — `proposal_form()` and `proposals_list()` in `web/components/proposal_form.py` are fully built but never imported into `web/components/version_detail.py`. See full finding under [Proposals & Synthesis](#proposals--synthesis) in section (c).

## (b) Newly Reported Symptoms

**Artifact Labeling Not Visible:** Static inspection found **no code-level gap**. Tags are persisted end-to-end (`ArtifactRow.tags` serialized via `json.dumps`/`json.loads` in `contexta/api/repositories.py`), returned by the API (`contexta/api/routers/artifacts.py`, `ArtifactItem`/`ArtifactResponse`/`ArtifactInVersion` schemas all declare `tags: List[str] = []`), and rendered on all three inspected UI surfaces — directly in `triage_widget.py` (`rx.foreach(artifact["tags"]...)` under a "Tags" column) and `version_detail.py` (same pattern in the "Linked Artifacts" section), and transitively in `ingestion_modal.py` via its embedded `triage_widget()`. Because static analysis cannot explain a reported "not visible" symptom when every code path renders the data, **this finding requires runtime/browser verification before it can be closed**, per design.md's Error Handling guidance (Requirement 4.4). Candidate runtime-only causes that were NOT verifiable statically: the separate `tag_suggestion_chips()` component used in the ingestion form itself (not inspected — could be the actual bug site); Reflex state/Var propagation issues affecting `AppState.triage_artifacts`/`current_version_artifacts` at runtime; CSS/layout clipping (a fixed `width="160px"` tag column in `triage_widget.py`); or artifacts actually being stored with empty tag arrays at the data level. This is reported at the code level as `Fully_Implemented`, but explicitly **not closed** pending browser verification. See full finding under [Artifact Ingestion, Labeling & Triage](#artifact-ingestion-labeling--triage) in section (c).

**Missing Artifact Traceability:** Two distinct sub-findings. (1) Citation *data* (file path, excerpt) is fully implemented and reaches the UI as real pipeline data (`SourceCitation.file_path` in `contexta/models/citations.py` → `FindingItem.source_artifact`/`.citation` in `contexta/api/schemas.py` → rendered as plain text in `web/components/finding_card.py`) — this sub-feature is `Fully_Implemented`. (2) Citation *navigation* — clicking a citation to jump to the source artifact — is `Not_Implemented`: `finding_card.py` has zero `on_click`/`rx.link`/navigation logic anywhere. (3) A third, related sub-finding — persisting which artifacts were active at the time a specific review ran (review-run-scoped provenance) — is also `Not_Implemented`: no schema column or endpoint ties a `review_job` to an artifact snapshot, and the "Linked Artifacts" and "Review Runs" sections of `version_detail.py` are unlinked siblings with no cross-reference. See full finding under [Artifact Traceability / Citations](#artifact-traceability--citations) in section (c).

## (c) Full Scope Findings (by Functional Area)

### Review Linking & Prior Intelligence

**Gap_Item: Review Linking UI**
- Status_Classification: `Implemented_Not_Wired`
- Reasoning: Backend (`contexta/db/schema.py` schema v6 `review_links` table; `insert_review_links`/`get_linked_review_ids`/`list_linkable_reviews` in `contexta/api/repositories.py`) and API (`POST /api/reviews` in `contexta/api/routers/reviews.py` accepting `linked_review_ids` via `CreateReviewRequest` in `contexta/api/schemas.py`, with 422 validation of linked-job existence/completion; `GET /api/versions/{version_id}/reviews/linkable`; router registered in `contexta/api/__init__.py`) are complete and correctly wired. UI is not: `web/pages/run_review.py` has the linking `rx.cond` block explicitly disabled, rendering `rx.text("", width="0")` instead; `web/components/review_link_selector.py` defines `review_link_selector(version_id)` fully but has zero import/call sites anywhere in `web/`.
- requirement_ref: project-contexta Req 3.1/3.2 (mixed); reported symptom "Review Linking"; Core_Gaps_Spec item 1

**Gap_Item: Prior Review Intelligence injection (positive confirmation)**
- Status_Classification: `Fully_Implemented`
- Reasoning: `_build_prior_intelligence(conn, review_id)` in `contexta/api/pipeline_bridge.py` is implemented and actually invoked in the review pipeline (mutates `blueprint.master_prompt_text` before prompt construction, confirmed at the call site around line 337 of `pipeline_bridge.py`). Works correctly end-to-end; not a gap.
- requirement_ref: project-contexta Req 3.1/3.2

### Proposals & Synthesis

**Gap_Item: Project-Scoped Proposal Listing**
- Status_Classification: `Implemented_Differently` (divergence takes precedence per Property 2; an `Implemented_Not_Wired` UI factor also applies)
- Reasoning: `contexta/api/routers/proposals.py` and `list_proposals_for_version` in `contexta/api/repositories.py` enforce an actively-guarded `WHERE rj.version_id = ?` filter (422 on cross-version mismatch) — i.e. version-scoped, not project-scoped. The originally reported expectation was project-wide aggregation; `project-contexta/requirements.md` doesn't mention "proposal" at all, so the divergence is against the user's reported expectation rather than a written spec. On top of the scope divergence, the UI is unwired: `proposal_form(version_id)` and `proposals_list(version_id)` in `web/components/proposal_form.py` are fully built (form + review checkboxes bound to `AppState.submit_version_proposal`; history list bound to `AppState.version_proposals`) but `web/components/version_detail.py` has zero import/call site for either.
- requirement_ref: reported symptom "Project-Scoped Proposals"; Core_Gaps_Spec items 2, 11

### Fork / Node Branching

**Gap_Item: Fork Iteration UI**
- Status_Classification: `Implemented_Not_Wired`
- Reasoning: Backend/API complete — `POST /nodes/{node_id}/fork` in `contexta/api/routers/nodes.py` validates input and calls real `db_repo.fork_node`, maps `ValueError`→404, returns 201; covered by `tests/test_db.py::test_fork_node` and `tests/test_e2e_integration.py::test_fork_node_creates_new_node`; `nodes.router` registered in `contexta/api/__init__.py`. UI handler `fork_node(node_id, name)` plus dialog state (`_fork_name`, `_fork_dialog_open`, `open_fork_dialog()`, `set_fork_name()`, `close_fork_dialog()`) exist fully in `web/state.py` (~lines 1193-1228), but a repo-wide search for "Fork"/`open_fork_dialog`/`_fork_dialog_open`/`fork_name` across all `web/components/*.py`, `web/pages/*.py`, `web/web.py` returns zero matches — no button or dialog anywhere, including `version_detail.py`'s `_action_bar()` next to "Run Review"/"Export JSON".
- requirement_ref: Core_Gaps_Spec item 3 (Fork Iteration); project-contexta mixed criterion (Fork mechanic + web-realizable intent)

### Scope Policy & Routing Decisions

**Gap_Item: Scope Policy / Routing Decision UI**
- Status_Classification: `Implemented_Not_Wired`
- Reasoning: `POST /nodes/{node_id}/routing-decision` in `contexta/api/routers/nodes.py` (`record_routing_decision`) validates input and persists via real `update_node_metadata` (actual `UPDATE nodes SET metadata_json...` + commit) in `contexta/api/repositories.py`; `nodes.router` registered in `contexta/api/__init__.py`. `web/components/scope_policy_panel.py` defines a fully-built `scope_policy_panel()` correctly bound to `AppState.submit_routing_decision`/`AppState._toggle_routing_edit` (both real in `web/state.py`), but a grep across the entire `web/` tree (`review_detail.py`, `content_pane.py`, `layout.py`, `version_detail.py`, `run_review.py`, `admin.py`) finds zero import/call sites outside its own definition file.
- requirement_ref: Core_Gaps_Spec item 5 (Scope Policy UI); project-contexta Req 2.3 (mixed)

### JSON Export

**Gap_Item: JSON Export UI**
- Status_Classification: `Implemented_Not_Wired`
- Reasoning: `GET /nodes/{node_id}/export` in `contexta/api/routers/nodes.py` builds a real `JSONPacket` with `schema_version=EXPORT_SCHEMA_VERSION` explicitly set, streams `application/json` with `Content-Disposition: attachment`, 404s if the node is missing — a full implementation, not a stub; registered via `nodes.router` in `contexta/api/__init__.py`. Recursive grep across all of `web/**/*.py*` for `fork|Export|export|/nodes/` returns zero matches for an export UI affordance. `web/components/node_detail.py` (the most plausible location) only has loading/empty states and a read-only JSON `code_block` view — no export/download button. Unlike Import, there is no dedicated export component file at all.
- requirement_ref: Core_Gaps_Spec item 6 (JSON Export); project-contexta mixed criterion

### JSON Import

**Gap_Item: JSON Import**
- Status_Classification: `Fully_Implemented` (end-to-end user-facing flow works; code-hygiene note below is not a functional gap)
- Reasoning: `POST /admin/import` in `contexta/api/routers/admin.py` decodes uploaded bytes and validates via `JSONPacket.model_validate_json(raw_text)` (422 on failure) strictly before any DB write; `admin.router` registered in `contexta/api/__init__.py`. `web/pages/admin.py` has its own inline `_import_section()` (lines ~257-291) bound to `AppState.handle_import`, and IS called from `admin_page()`'s render tree (line ~607) — so the Admin page renders a working import UI in practice. `AppState.handle_import` (`web/state.py` ~1290-1313) correctly builds multipart form data and POSTs to `/api/admin/import`.
- Code-hygiene note (not a functional gap): `web/components/import_panel.py` defines a separate, nearly identical `import_panel()` that is orphaned — zero import/call sites anywhere outside its own file.
- requirement_ref: Core_Gaps_Spec item 7 (JSON Import)

### Dream Cycle

**Gap_Item: Dream Cycle**
- Status_Classification: `Fully_Implemented` (with a minor caveat noted below)
- Reasoning: `contexta/api/routers/admin.py` implements `_dream_cycle_state`, `_run_dream_cycle_task` (instantiates `DreamCycleWorker` from `contexta.admin.dream_cycle`, calls `worker.run(conn)`), `POST /admin/dream-cycle` (202/409), `GET /admin/dream-cycle/status`; `admin.router` registered in `contexta/api/__init__.py`. `web/state.py`'s `AppState.trigger_dream_cycle()`/`fetch_dream_cycle_status()` POST/GET the real endpoints. `web/pages/admin.py`'s `_dream_cycle_section()` renders status via `rx.cond` chains and an `rx.button("Run Dream Cycle", ...)`, called inside `admin_page()`'s render tree, reachable at `/admin`.
- Caveat: `AppState.fetch_dream_cycle_status()` is defined but never called anywhere (not wired into `load_admin_page()`'s `on_load` or any polling loop) — status only updates after the user's own trigger action in the same session; a fresh page load or externally-triggered status change won't be reflected. Does not change the classification.
- requirement_ref: Core_Gaps_Spec item 8 (Dream Cycle)

### Blueprint Management

**Gap_Item: Blueprint Management**
- Status_Classification: `Fully_Implemented` (with a minor caveat noted below; same orphaned-dedicated-component pattern as Import)
- Reasoning: `GET/POST /admin/blueprints` and `POST /admin/blueprints/{id}/activate` in `contexta/api/routers/admin.py` call real `list_blueprints`/`save_blueprint_version`/`activate_blueprint`; `admin.router` registered in `contexta/api/__init__.py`. `web/pages/admin.py` has its own inline `_blueprint_section()`, rendered inside `admin_page()`, bound to `AppState.create_blueprint(...)`/`AppState.activate_blueprint(bp["id"])`, table driven by `AppState.admin_blueprints`; `web/state.py` confirms `fetch_blueprints()`/`create_blueprint()`/`activate_blueprint()` all work and re-invoke `fetch_blueprints()` after create/activate.
- Caveat: `load_admin_page()`'s `on_load` handler never calls `fetch_blueprints()` on initial page load — table is empty until the first create/activate action triggers an internal refetch. `web/components/blueprint_panel.py` defines a dedicated `blueprint_panel()` that is dead code, never imported/called anywhere. UX gap noted but does not change classification.
- requirement_ref: Core_Gaps_Spec item 9 (Blueprint Management)

### Global Client Insights Sidebar

**Gap_Item: Insights Sidebar**
- Status_Classification: `Implemented_Not_Wired`
- Reasoning: `GET /insights` in `contexta/api/routers/insights.py` queries `global_client_insights` ordered by `frequency_count DESC LIMIT 10`, returns real `InsightsResponse`/`InsightItem`; `insights.router` registered in `contexta/api/__init__.py` (line 166). `web/components/insights_sidebar.py` is a complete component (`insights_sidebar()`, `_insight_card()`, accordion UI, badge count, `rx.foreach` over `AppState.insights`), but it is never imported/called from `run_review.py`, `admin.py`, or any other component. Worse than the typical unwired pattern: a case-insensitive grep for `insight`/`Insight` across `web/state.py` returns zero matches — there is no `fetch_insights` handler and no `AppState.insights` attribute at all, so the component references nonexistent state and would error if ever rendered.
- requirement_ref: Core_Gaps_Spec item 10 (Insights Sidebar)

### Artifact Ingestion, Labeling & Triage

**Gap_Item: Artifact Labeling visibility (newly reported symptom)**
- Status_Classification: `Fully_Implemented` at the code level, **with an explicit runtime-verification caveat — not closed**
- Reasoning: Tags are persisted (`contexta/api/repositories.py` `ArtifactRow.tags`; `create_artifact()` via `json.dumps(tags)`; `_row_to_artifact()` via `json.loads(row["tags"] or "[]")` on every read path), returned by the API (`contexta/api/routers/artifacts.py` POST/GET/PATCH all echo `tags`; `contexta/api/schemas.py` `ArtifactItem`/`ArtifactResponse`/`ArtifactInVersion` all declare `tags: List[str] = []`), and rendered directly in `triage_widget.py` (`rx.foreach(artifact["tags"].to(list[str]), lambda t: rx.badge(t, ...))` under a "Tags" column) and `version_detail.py` (same pattern in "Linked Artifacts"), and transitively in `ingestion_modal.py` via its embedded `triage_widget()` (note: `ingestion_modal.py`'s own "Tags" section calls a different component, `tag_suggestion_chips()`, for in-progress upload suggestions, not persisted `artifact.tags`). Because static inspection found tags persisted, returned, and rendered on all three surfaces, the report cannot statically explain a "not visible" symptom — per design.md's Error Handling guidance (Requirement 4.4), this is flagged as requiring runtime/browser verification. Candidate runtime-only causes NOT verifiable statically: `tag_suggestion_chips()`'s own implementation (not inspected); Reflex state/Var propagation issues for `AppState.triage_artifacts`/`current_version_artifacts`; CSS/layout clipping (fixed `width="160px"` tag column in `triage_widget.py`); artifacts actually stored with empty tags at the data level.
- requirement_ref: newly reported symptom "Artifact Labeling Not Visible"; project-contexta Req 4 area

**Gap_Item: MCP Host Client never wired into artifact ingestion**
- Status_Classification: `Implemented_Not_Wired`
- Reasoning: `contexta/mcp/client.py` (`MCPHostClient`, supports `connect_stdio`/`connect_sse`) and `contexta/mcp/artifact_registry.py` (`ArtifactRegistry`) are fully built, but have zero references outside `contexta/mcp/` and `tests/`. Web ingestion instead uses a wholly separate `POST /api/artifacts` upload/paste/url mechanism with no MCP transport (`web/components/ingestion_modal.py`).
- requirement_ref: project-contexta Req 4.1

**Gap_Item: No line-count/content-preview data reaches the web layer**
- Status_Classification: `Not_Implemented`
- Reasoning: The `artifacts` table (`contexta/db/schema.py`) has no `line_count` column; `contexta/api/schemas.py` exposes no line-count/content field; no such data appears in `ingestion_modal.py`, `triage_widget.py`, or `version_detail.py`.
- requirement_ref: project-contexta Req 4.2, 4.3, 4.4

### Artifact Traceability / Citations

**Gap_Item: Citation data reaching the UI (positive confirmation)**
- Status_Classification: `Fully_Implemented`
- Reasoning: `contexta/models/citations.py`'s `SourceCitation` has a real, pydantic-validated `file_path` field (plus `line_start`/`line_end`/`citation_type`/`excerpt`), populated by the review pipeline per Finding. `contexta/api/routers/reviews.py`'s `_build_review_payload` (~lines 103-112) pulls `f.citations[0].file_path`/`.excerpt` (real pipeline data) into `FindingItem.source_artifact`/`.citation` (`contexta/api/schemas.py` lines ~142-148). Minor additional gap: only `citations[0]` is surfaced — subsequent citations on a finding with multiple citations are silently dropped in the API response.
- requirement_ref: newly reported symptom "Missing Artifact Traceability"; project-contexta Req 5 area (5.1-5.6)

**Gap_Item: Citation navigation (click-to-jump)**
- Status_Classification: `Not_Implemented`
- Reasoning: `web/components/finding_card.py` renders `finding["source_artifact"]` and `finding["citation"]` via plain `rx.text(...)` only. A full-file search for `on_click`, `rx.link`, `navigate`, `redirect` returns zero matches — no click handler, no `rx.link`, no routing logic anywhere. Distinguishing "citation text is shown" (works, see above) from "citation is a navigable reference" (does not exist), per Requirement 5.4.
- requirement_ref: newly reported symptom "Missing Artifact Traceability"; project-contexta Req 5.4

**Gap_Item: Review-run-scoped artifact provenance (snapshot linking)**
- Status_Classification: `Not_Implemented`
- Reasoning: `artifact_version_links` is version-scoped and mutable (artifacts can be added/removed/toggled after a review runs); `review_jobs` has no column capturing which artifacts were active at the time any specific review executed — no persisted snapshot (`contexta/db/schema.py`, `contexta/api/repositories.py`). No endpoint ties a `review_job` to a specific artifact set (`contexta/api/pipeline_bridge.py`, `contexta/api/routers/reviews.py`, `contexta/api/routers/versions.py`). In the UI, `current_version_artifacts` (`web/state.py`) and "Linked Artifacts" in `version_detail.py` only ever reflect the version's *current* artifact set; "Linked Artifacts" and "Review Runs" are unlinked sibling sections with no cross-reference between a review row and the artifacts that produced it.
- requirement_ref: newly reported symptom "Missing Artifact Traceability"; project-contexta Req 5 area (5.1-5.6)

### Projects, Versions & Navigation

**Gap_Item: Web layer never uses env-var LLM backend selection**
- Status_Classification: `Implemented_Differently`
- Reasoning: `contexta/config.py`'s `ContextaConfig` exists but only for the TUI path. `contexta/api/pipeline_bridge.py::resolve_llm_config` reads DB-stored `app_config` keys for 3 hardcoded providers instead of an arbitrary env-var-injected LiteLLM provider/model string. UI (`web/pages/admin.py` API-key inputs) exists. No boot-time halt for missing config in the web path — failures are deferred to review-trigger time as a job `progress_message` rather than the TUI's fatal-error-and-halt behavior.
- requirement_ref: project-contexta Req 1.4, 1.5

**Gap_Item: No single persistent header combining project name + active node name**
- Status_Classification: `Implemented_Differently`
- Reasoning: Backend/API/UI all exist, but differently than specified: `web/components/sidebar.py` shows a static "Contexta" title; `node_detail.py`/`version_detail.py` each render their own local per-view heading instead of one persistent app-wide header.
- requirement_ref: project-contexta Req 10.1

**Gap_Item: No persistent left-pane file/artifact browser with line references**
- Status_Classification: `Not_Implemented`
- Reasoning: Same root cause as the line-count gap above — no line-reference data exists anywhere in the backend. `web/components/sidebar.py` renders a Project→Version→Node tree, not a file browser; artifacts only appear in `version_detail.py`'s "Linked Artifacts" section without line references.
- requirement_ref: project-contexta Req 10.2

**Gap_Item: Right-pane review view aggregates 12 dimensions into 5 summary categories**
- Status_Classification: `Implemented_Differently`
- Reasoning: All 12 `ReviewNodePayload` objects are stored per node via `contexta/pipeline/dimension_runner.py::commit_exploration_node` (backend_exists true). `contexta/api/routers/reviews.py::_build_review_payload` flattens findings into 5 buckets via `_DIMENSION_CATEGORY` (api regroups rather than passing through 12 axes). `web/components/review_detail.py` + `finding_card.py` render 5 count pills and a flat finding-card list; the original dimension name survives only as a small per-card badge.
- requirement_ref: project-contexta Req 10.3

**Gap_Item: SQLite Data Layer (positive confirmation)**
- Status_Classification: `Fully_Implemented` (exceeds original scope)
- Reasoning: `contexta/db/schema.py` creates all required tables plus extensions (`versions`, `artifacts`, `artifact_version_links`, `review_jobs`, `proposal_jobs`, `app_config`, `reviews`, `review_links`, `proposal_review_links`). Payload validation before commit enforced via `DimensionValidationError` in `dimension_runner.py`. Project/version bootstrapping fully wired: `contexta/api/routers/projects.py` + `versions.py` ↔ `web/components/sidebar.py` (`create_project`) and `triage_widget.py` (`create_version_from_triage`).
- requirement_ref: project-contexta Req 2.1-2.7

**Gap_Item: Node/version mouse-based switching (positive confirmation)**
- Status_Classification: `Fully_Implemented`
- Reasoning: `on_click=AppState.select_node(...)` bindings exist in `sidebar.py` and `version_detail.py::_node_row`, covering the web-realizable portion of Requirement 10.7 (mouse navigation).
- requirement_ref: project-contexta Req 10.7 (web-realizable portion only; keyboard/footer-key portion is tui_only)

**Gap_Item: Container bootstrapping (positive confirmation)**
- Status_Classification: `Fully_Implemented` (web-realizable portion)
- Reasoning: `Dockerfile`/`entrypoint.sh`/`docker-compose.yml` correctly describe single-process/single-port-8000 deployment via `reflex run --backend-only`.
- Note (not a gap, code hygiene): `supervisord.conf` describes a stale two-process/two-port architecture that `entrypoint.sh`'s actual `ENTRYPOINT` never invokes — orphaned config.
- requirement_ref: project-contexta Req 1.1-1.3

Cross-reference: Requirement 7 (Fork Iteration) is fully subsumed by the Fork/Node Branching section above. Requirement 4.5 (citation-to-artifact association) is subsumed by the Artifact Traceability / Citations section. Requirement 10.4/10.5/10.6/10.8/10.9 are `tui_only` per the exclusion filter and produced no Gap_Item. Requirement 10 (TUI Layout and Navigation) is entirely `tui_only` (10.1-10.9) and excluded except where a web-realizable portion is noted above (10.1, 10.2, 10.3, and the mouse-navigation portion of 10.7).

## (d) Re-verification of the 11 Core_Gaps_Spec Items

| # | Gap (from core-scope-gaps-implementation) | Prior Status (tasks.md) | Current Status (this audit) | Changed? | Evidence |
|---|---|---|---|---|---|
| 1 | Review Linking | unchecked (`[ ]`) | `Implemented_Not_Wired` | Yes — unchecked implied "not started," but backend+API are fully done; only the UI is missing | `review_links` table + `POST /api/reviews` fully wired; `run_review.py`'s linking `rx.cond` is explicitly disabled; `review_link_selector.py` unused |
| 2 | Proposal Re-Architecture | unchecked (`[ ]`) | `Implemented_Differently` | Yes — backend/API done but scoped per-version rather than per-project (user expectation), and UI is missing | `proposals.py` enforces version-scoped `WHERE rj.version_id = ?` with 422 guard; `proposal_form.py`/`proposals_list()` never imported into `version_detail.py` |
| 3 | Fork Iteration | unchecked (`[ ]`) | `Implemented_Not_Wired` | Yes | `POST /nodes/{node_id}/fork` + `fork_node` fully wired and tested; zero UI call sites for `fork_node`/`open_fork_dialog` anywhere in `web/` |
| 4 | Proactive Advisor | unchecked (`[ ]`) | `Implemented_Not_Wired` | Yes | `ProactiveAdvisor.evaluate` + `POST /api/proposals/{id}/acknowledge` full status-machine round trip works; `AppState.acknowledge_proposal` has zero UI call sites; `status_banner.py` shows only a raw badge |
| 5 | Scope Policy UI | unchecked (`[ ]`) | `Implemented_Not_Wired` | Yes | `POST /nodes/{node_id}/routing-decision` fully wired; `scope_policy_panel.py` built but zero call sites in `web/` |
| 6 | JSON Export | unchecked (`[ ]`) | `Implemented_Not_Wired` | Yes | `GET /nodes/{node_id}/export` fully implemented, not a stub; zero export UI affordance anywhere in `web/` |
| 7 | JSON Import | unchecked (`[ ]`) | `Fully_Implemented` | Yes — actually complete end-to-end, despite an orphaned dedicated component | `POST /admin/import` fully validated; `admin.py`'s inline `_import_section()` is rendered and works; `import_panel.py` is orphaned dead code |
| 8 | Dream Cycle | unchecked (`[ ]`) | `Fully_Implemented` | Yes — complete, with a minor status-refresh caveat | `POST /admin/dream-cycle` + `_dream_cycle_section()` fully wired and rendered at `/admin`; `fetch_dream_cycle_status()` never called on load |
| 9 | Blueprint Management | unchecked (`[ ]`) | `Fully_Implemented` | Yes — complete, with a minor initial-load caveat | `admin.py`'s inline `_blueprint_section()` fully wired; `load_admin_page()` never calls `fetch_blueprints()` on load; `blueprint_panel.py` orphaned |
| 10 | Insights Sidebar | unchecked (`[ ]`) | `Implemented_Not_Wired` | Yes, and worse than typical | `GET /insights` fully wired; `insights_sidebar.py` unused AND `AppState.insights`/`fetch_insights` don't exist at all — would error if rendered |
| 11 | Version-Level Proposal Listing | unchecked (`[ ]`) | `Implemented_Differently` | Yes — same finding as #2; backend/API exists version-scoped, UI (`proposals_list`) not wired | Same evidence as row 2 |

All 11 items' prior status in `core-scope-gaps-implementation/tasks.md` is unchecked (`[ ]`) for every single task ID across the entire file — confirmed by direct read.

## (e) Tracking_Gap

The entire backend/API layer task set in `core-scope-gaps-implementation/tasks.md` is marked unchecked despite being fully implemented in actual code (confirmed across the functional-area findings in section (c)):

- **Unchecked but fully implemented (backend/API):** 1.1, 2.1, 2.2, 2.3, 3.1, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 8.1, 8.2, 10.1, 10.2, 10.3, 11.1, 12.1
- **Unchecked but the AppState handlers already exist fully-built in `web/state.py`:** 14.1 (review linking/proposals handlers), 15.1 (fork/routing/export handlers), 16.1 (admin feature handlers) — e.g. `fork_node`, `submit_routing_decision`, `trigger_dream_cycle`, `fetch_dream_cycle_status`, `fetch_blueprints`, `create_blueprint`, `activate_blueprint`, `acknowledge_proposal`, `handle_import` all exist and work.
- **Ambiguous "exists but orphaned" cases (neither cleanly checked nor unchecked):** 16.3 (`blueprint_panel.py`) and 16.4 (`import_panel.py`) — the component files exist and are complete, but are dead code never wired to the reachable Admin page (which instead uses separately-written inline duplicates). Flagged explicitly as not fully consistent with either a checked or unchecked interpretation.
- **Correctly unchecked, correctly reflecting genuinely missing/unwired UI work:** 14.2, 14.3 (`review_link_selector.py`, `proposal_form.py` exist but unused — same "built but orphaned" pattern as 16.3/16.4), 15.2, 15.3 (`scope_policy_panel.py` exists but unused; Fork/Export buttons genuinely don't exist), 17.1, 17.2 (insights sidebar UI genuinely unwired, and its state doesn't exist; advisor acknowledgement dialog genuinely doesn't exist), 17.3 (advisor acknowledgement dialog).
- **Discrepancy to flag specifically:** task 16.2 (Dream Cycle UI) remains unchecked, but the dream-cycle UI actually IS present via `admin.py`'s inline implementation — another checked/unchecked mismatch.

## (f) Scripts_Markdown_Note

`/scripts` contains **no markdown files**. Its actual contents, confirmed via direct listing, are:

- `dev-start.sh`
- `healthcheck.sh`
- `init_db.py`
- `__pycache__/` (a build artifact directory, not source — excluded from the above as not a script)
