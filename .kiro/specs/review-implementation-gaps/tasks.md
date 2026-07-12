# Implementation Plan: Review Implementation Gaps (Audit)

## Overview

This is a read-only investigative audit, not a code-building feature. Every task below is a static-inspection or report-writing step executed with `read_files` / `grep_search` / `list_directory` / `execute_bash` (for `git status` only). No source code, schema, or configuration file is created, modified, or deleted at any point. The sole deliverable is `.kiro/specs/review-implementation-gaps/gap-analysis.md`, assembled after all investigation tasks complete and self-checked against the design's Correctness Properties and Testing Strategy before being considered final.

## Tasks

- [x] 1. Scope enumeration and Web_Scope filtering
  - [x] 1.1 Enumerate and classify all acceptance criteria in `.kiro/specs/project-contexta/requirements.md` Requirements 1–14
    - For each acceptance criterion, classify as `tui_only`, `mixed`, or `web` per the filter rule (keyboard nav, footer key bindings, TUI pane layout, `CitationJumpRequested`, Admin Tab screen navigation = `tui_only`; TUI mechanic + web-realizable intent = `mixed`; no TUI mechanic = `web`)
    - Produce the ordered Web_Scope item list (one `Gap_Item` candidate per `mixed`/`web` criterion, noting the excluded TUI-only portion for `mixed` items) that feeds tasks 2–14
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ]* 1.2 Self-check scope classification against Property 7
    - **Property 7: Scope filtering is a total, consistent classification over criteria**
    - **Validates: Requirements 1.1, 1.2, 1.3**
    - Confirm every criterion from Requirements 1–14 received exactly one of `{tui_only, mixed, web}`, that no `tui_only` criterion produced a `Gap_Item`, and that every `mixed`/`web` criterion produced exactly one `Gap_Item`

- [x] 2. Investigate Review Linking & Prior Review Intelligence (originally reported issue; Core_Gaps_Spec item 1)
  - [x] 2.1 Verify backend existence and API wiring for review linking
    - Backend-existence check: `grep_search` for `review_links` table/DDL in `contexta/db/schema.py`, and for `insert_review_links` / `get_linked_review_ids` / `list_linkable_reviews` in `contexta/api/repositories.py`
    - API-wiring check: confirm `POST /api/reviews` accepts `linked_review_ids` and `GET /api/versions/{version_id}/reviews/linkable` exist in `contexta/api/routers/reviews.py`, and that the router is `include_router`'d in `contexta/api/app.py`
    - _Requirements: 3.1, 3.2, 6.1_

  - [x] 2.2 Verify UI rendering for review linking and Prior Review Intelligence injection
    - UI-rendering check: `grep_search` for `review_link_selector` inside `web/pages/run_review.py` and confirm whether the `rx.cond` block wrapping it is disabled/commented, per Requirement 3.1
    - Verify `web/components/review_link_selector.py` exists but is unused (no import/call site)
    - Verify `_build_prior_intelligence` (or equivalent) exists in `contexta/api/pipeline_bridge.py` and is actually invoked when constructing the prompt
    - _Requirements: 3.1, 3.2, 6.1_

- [x] 3. Investigate Proposals & Synthesis (originally reported issue; Core_Gaps_Spec items 2 and 11)
  - [x] 3.1 Verify proposal backend/API scope boundary (version-scoped vs project-scoped)
    - Backend/API check: inspect `contexta/api/routers/proposals.py` to confirm whether proposal aggregation is scoped to a single version rather than across all versions of a project, per Requirement 3.3
    - Cross-check `list_proposals_for_version` in `contexta/api/repositories.py` for the same scoping boundary
    - _Requirements: 3.3, 6.1_

  - [x] 3.2 Verify version-level proposal UI wiring
    - `grep_search` for `proposal_form` and `proposals_list` inside `web/components/version_detail.py` to confirm whether either is imported/rendered
    - Record the specific missing render call if absent, per Requirement 3.4
    - _Requirements: 3.4, 6.1_

- [x] 4. Investigate Fork / Node Branching (Core_Gaps_Spec item 3)
  - [x] 4.1 Verify fork backend existence, API wiring, and UI rendering
    - Backend/API: `grep_search` for `POST /api/nodes/{node_id}/fork` in `contexta/api/routers/nodes.py` and confirm router registration in `contexta/api/app.py`
    - UI: confirm a "Fork" action exists and is bound to a handler (e.g. `fork_node`) in the review/version detail component and `web/state.py`
    - _Requirements: 6.1, 6.2_

- [x] 5. Investigate Proactive Advisor (Core_Gaps_Spec item 4)
  - [x] 5.1 Verify advisor backend existence, API wiring, and UI rendering
    - Backend/API: confirm advisor evaluation call site (e.g. `ProactiveAdvisor.evaluate`) in `contexta/api/pipeline_bridge.py` or `contexta/api/routers/proposals.py`, and `POST /api/proposals/{proposal_id}/acknowledge`
    - UI: confirm an acknowledgement dialog exists and is bound to `acknowledge_proposal` in `web/state.py` and rendered in a reachable proposal view component
    - _Requirements: 6.1, 6.2_

- [x] 6. Investigate Scope Policy & Routing Decisions (Core_Gaps_Spec item 5)
  - [x] 6.1 Verify scope policy backend existence, API wiring, and UI rendering
    - Backend/API: confirm `POST /api/nodes/{node_id}/routing-decision` in `contexta/api/routers/nodes.py` and `update_node_metadata` in `contexta/api/repositories.py`
    - UI: `grep_search` for a routing-toggle component (e.g. `scope_policy_panel`) and confirm it is imported/rendered from a reachable page and bound to the routing-decision handler in `web/state.py`
    - _Requirements: 2.3, 6.1, 6.2_

- [x] 7. Investigate JSON Export (Core_Gaps_Spec item 6)
  - [x] 7.1 Verify export backend existence, API wiring, and UI rendering
    - Backend/API: confirm `GET /api/nodes/{node_id}/export` in `contexta/api/routers/nodes.py` returns a `schema_version` field
    - UI: confirm an "Export JSON" button exists and links/navigates to the export endpoint from a reachable component
    - _Requirements: 6.1, 6.2_

- [x] 8. Investigate JSON Import (Core_Gaps_Spec item 7)
  - [x] 8.1 Verify import backend existence, API wiring, and UI rendering
    - Backend/API: confirm `POST /api/admin/import` in `contexta/api/routers/admin.py` validates against schema before any DB write
    - UI: `grep_search` for an import/upload component (e.g. `import_panel`) and confirm it is imported/rendered on the Admin page and posts to the import endpoint
    - _Requirements: 6.1, 6.2_

- [x] 9. Investigate Dream Cycle (Core_Gaps_Spec item 8)
  - [x] 9.1 Verify Dream Cycle backend existence, API wiring, and UI rendering
    - Backend/API: confirm `POST /api/admin/dream-cycle` and `GET /api/admin/dream-cycle/status` in `contexta/api/routers/admin.py`
    - UI: `grep_search` for a Dream Cycle trigger/status component (e.g. `dream_cycle_panel`) and confirm it is imported/rendered on the Admin page and bound to the handlers in `web/state.py`
    - _Requirements: 6.1, 6.2_

- [x] 10. Investigate Blueprint Management (Core_Gaps_Spec item 9)
  - [x] 10.1 Verify Blueprint backend existence, API wiring, and UI rendering
    - Backend/API: confirm `GET/POST /api/admin/blueprints` and `POST /api/admin/blueprints/{id}/activate` in `contexta/api/routers/admin.py`
    - UI: `grep_search` for a blueprint management component (e.g. `blueprint_panel`) and confirm it is imported/rendered on the Admin page and bound to `fetch_blueprints`/`create_blueprint`/`activate_blueprint` in `web/state.py`
    - _Requirements: 6.1, 6.2_

- [x] 11. Investigate Global Client Insights Sidebar (Core_Gaps_Spec item 10)
  - [x] 11.1 Verify Insights backend existence, API wiring, and UI rendering
    - Backend/API: confirm `GET /api/insights` in `contexta/api/routers/insights.py` and confirm the router is registered in `contexta/api/app.py`
    - UI: `grep_search` for an insights sidebar component (e.g. `insights_sidebar`) and confirm it is imported/rendered from a reachable page and bound to `fetch_insights` in `web/state.py`
    - _Requirements: 6.1, 6.2_

- [x] 12. Investigate Artifact Labeling (newly reported symptom)
  - [x] 12.1 Trace tag/label data path from upload through storage to every UI surface
    - Inspect `contexta/api/routers/artifacts.py`, `contexta/api/repositories.py`, and `contexta/api/schemas.py` to confirm tags/labels are persisted and returned by the API
    - Inspect `web/components/ingestion_modal.py`, `web/components/triage_widget.py`, and `web/components/version_detail.py` for a render call (`rx.text`, `rx.foreach`, etc.) referencing the tag/label field
    - For each surface, record persisted/returned/rendered status; if all three surfaces render it, flag the discrepancy with the reported symptom as requiring runtime/browser verification
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 13. Investigate Artifact Traceability / Citations (newly reported symptom)
  - [x] 13.1 Trace citation and provenance data from source model through API to finding display
    - Inspect `contexta/models/citations.py` (`SourceCitation.file_path`) and `contexta/api/routers/reviews.py` (`FindingItem.source_artifact`, `FindingItem.citation`) for population with real artifact references
    - Inspect `web/components/finding_card.py` for whether these fields are rendered, and whether rendering is a navigable reference (e.g. link/click handler back to the artifact) or plain text only
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 13.2 Verify artifact-version link exposure for review-run provenance
    - `grep_search` for `artifact_version_links` (backend table/repository usage) and `current_version_artifacts` in `web/state.py`
    - Determine whether any UI surface connects a review's findings back to which artifacts were active for that specific review run
    - _Requirements: 5.5, 5.6_

- [x] 14. Investigate remaining Projects, Versions & Navigation Web_Scope items
  - [x] 14.1 Verify web-realizable coverage of remaining Web_Scope items from Requirements 1, 2, 4, 7, and 10 (project bootstrapping, SQLite data layer exposure, MCP-derived artifact browsing, node/version navigation) not already covered by tasks 2–13
    - Cross-reference the Web_Scope list from task 1.1 against tasks 2–13 to identify any remaining `mixed`/`web` items and inspect the relevant `contexta/api/routers/`, `contexta/db/`, and `web/pages/`, `web/components/` files for each
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 15. Checkpoint — review investigation findings before re-verification pass
  - Ensure all tasks 1–14 have recorded evidence (backend_exists, api_wired, ui_rendered, diverges_from_spec) with cited file paths, ask the user if questions arise.

- [x] 16. Re-verify the 11 Core_Gaps_Spec items and cross-reference tasks.md
  - [x] 16.1 Build the re-verification table for all 11 Core_Gaps_Spec items
    - Using evidence gathered in tasks 2–11 (Review Linking, Proposal Re-Architecture, Fork, Proactive Advisor, Scope Policy UI, JSON Export, JSON Import, Dream Cycle, Blueprint Management, Insights Sidebar, Version-Level Proposal Listing), state whether each item's implicit "not implemented" status from `core-scope-gaps-implementation/tasks.md` still holds or has changed
    - _Requirements: 6.1, 6.2_

  - [x] 16.2 Identify Tracking_Gap discrepancies against `core-scope-gaps-implementation/tasks.md`
    - Cross-reference each re-verified gap's current status against its corresponding unchecked task ID(s) in `core-scope-gaps-implementation/tasks.md` (e.g. tasks 5.1–5.3 for Review Linking, 6.1–6.3 for Proposal Re-Architecture, 7.1 for Fork, 7.2 for Scope Policy, 7.3 for Export, 10.1 for Import, 10.2 for Dream Cycle, 10.3 for Blueprint, 11.1 for Insights, 6.2 for Version-Level Proposal Listing)
    - List which specific task IDs appear inconsistent with current code state
    - _Requirements: 6.3, 7.1, 7.2_

- [x] 17. Record the Scripts_Markdown_Note
  - [x] 17.1 Confirm `/scripts` directory contents and record the absence of markdown files
    - `list_directory` on `/scripts`, listing actual contents (e.g. `dev-start.sh`, `healthcheck.sh`, `init_db.py`) found during investigation
    - _Requirements: 8.1_

- [x] 18. Assemble and write the audit report
  - [x] 18.1 Write `gap-analysis.md` following the section structure from design.md
    - Sections: (a) TL;DR — Review_Linking_Finding and Project_Scoped_Proposal_Finding; (b) Newly Reported Symptoms — Artifact_Labeling_Finding and Artifact_Traceability_Finding; (c) Full Scope Findings by functional area (Review Linking & Prior Intelligence, Proposals & Synthesis, Fork / Node Branching, Scope Policy & Routing Decisions, JSON Export, JSON Import, Dream Cycle, Blueprint Management, Global Client Insights Sidebar, Artifact Ingestion Labeling & Triage, Artifact Traceability / Citations, Projects Versions & Navigation); (d) Re-verification table for the 11 Core_Gaps_Spec items; (e) Tracking_Gap; (f) Scripts_Markdown_Note
    - Apply the Classification Decision Procedure (divergence → backend absence → wiring gap → full implementation) to every `Gap_Item`'s evidence tuple from tasks 1–14, and use the results of task 16 for section (d)
    - Every `Gap_Item` entry includes title, `Status_Classification`, reasoning citing file paths/constructs, and the originating `project-contexta` requirement number or reported symptom name
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 18.2 Self-check the assembled report against Properties 1–6 and the read-only guarantee
    - **Property 1: Classification is total and deterministic** — **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
    - **Property 2: Divergence takes precedence over wiring state** — **Validates: Requirements 2.4**
    - **Property 3: Absence of backend implies Not_Implemented** — **Validates: Requirements 2.2**
    - **Property 4: Backend presence with incomplete wiring implies Implemented_Not_Wired** — **Validates: Requirements 2.3**
    - **Property 5: Full wiring implies Fully_Implemented** — **Validates: Requirements 2.5**
    - **Property 6: Every Gap_Item has exactly one valid status and non-empty cited reasoning** — **Validates: Requirements 2.1, 2.6, 9.2**
    - Walk every `Gap_Item` in sections (c) and (d) against its own evidence tuple; correct any entry that fails before finalizing
    - Run `git status` and confirm no file other than `gap-analysis.md` (and this spec's own artifacts) shows as modified, satisfying the read-only guarantee in Requirement 9.6
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 9.2, 9.6_

- [x] 19. Final checkpoint — Ensure the report is complete
  - Ensure `gap-analysis.md` contains all required sections and every Gap_Item passed self-check, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional self-check/verification steps and can be skipped for a faster pass, but skipping them means the corresponding Property is not confirmed before the report is finalized
- This audit produces no application code, so there is no unit-test or property-test suite added to the repository — "testing" here means the procedural verification and property-style self-check steps described in design.md's Testing Strategy section
- Each investigation task (2–14) independently records an `Evidence` tuple `(backend_exists, api_wired, ui_rendered, diverges_from_spec)` with cited file paths; task 18.1 applies the Classification Decision Procedure to every recorded tuple
- No task in this plan creates, modifies, or deletes any file other than `gap-analysis.md`
- Checkpoints ensure incremental validation before moving to report assembly

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "2.2", "3.1", "3.2", "4.1", "5.1", "6.1", "7.1", "8.1", "9.1", "10.1", "11.1", "12.1", "13.1", "13.2", "14.1", "17.1"] },
    { "id": 2, "tasks": ["16.1", "16.2"] },
    { "id": 3, "tasks": ["18.1"] },
    { "id": 4, "tasks": ["18.2"] }
  ]
}
```
