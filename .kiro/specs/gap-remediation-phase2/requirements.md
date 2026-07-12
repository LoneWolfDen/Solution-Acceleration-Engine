# Requirements Document

## Introduction

This spec covers Phase 2 remediation of the gaps documented in `.kiro/specs/review-implementation-gaps/gap-analysis.md`. That audit found that most backend/API work for the original 11 core gaps is complete, but a further set of items are either `Not_Implemented`, `Implemented_Not_Wired`, or `Implemented_Differently`. This document defines the requirements for closing those remaining items, split into three independently executable tracks so they can be implemented in parallel without merge conflicts:

- **Track A** — Backend: schema migrations, provenance snapshotting, artifact metadata, review payload fidelity.
- **Track B** — Frontend: mounting already-built-but-orphaned components into reachable pages.
- **Track C** — Frontend state: fixing typing blockers and adding the one missing state/handler pair.

Each track touches a disjoint set of files (see design.md's file ownership table) so that three agents can work simultaneously.

## Glossary

- **Snapshot_Provenance**: A persisted, immutable record of which artifacts were active at the moment a specific review job ran, distinct from the mutable "current" artifact set of a version.
- **Project_Scoped_Proposals**: Proposal aggregation across all versions of a project, additive to (not a replacement for) the existing version-scoped `list_proposals_for_version` behavior.
- **Dimension_Fidelity**: Returning all 12 original `ReviewDimensionEnum` axis labels on `FindingItem.type`, instead of remapping into the 5-bucket `_DIMENSION_CATEGORY` summary.
- **Citation_Array**: The full `SourceCitation` list for a finding, as opposed to only `citations[0]`.

## Requirements

### Requirement A1 — Project-Scoped Proposal Aggregation (additive)

**User Story:** As a reviewer, I want to see proposals aggregated across every version of a project, so that I can track synthesis history at the project level without losing the existing per-version view.

#### Acceptance Criteria

1. THE Web_API SHALL add `GET /api/projects/{project_id}/proposals` returning proposals for every review job belonging to any version under that project, without removing or weakening the existing `WHERE rj.version_id = ?` guard on `list_proposals_for_version` or the version-scoped endpoint.
2. THE existing `POST/GET /api/versions/{version_id}/proposals` endpoints and their 422 validation guards SHALL remain unchanged and continue to pass their existing tests in `tests/api/test_proposals.py`.
3. THE new endpoint SHALL return each proposal's `version_id` (added to `ProposalListItem`) so the UI can group/label proposals by version at the project level.
4. IF the specified project_id does not exist, THEN THE Web_API SHALL return HTTP 404.

### Requirement A2 — Review-Run Artifact Snapshot Provenance

**User Story:** As a reviewer, I want to know exactly which artifacts were active when a specific review ran, so that later artifact changes don't retroactively make old review provenance ambiguous.

#### Acceptance Criteria

1. WHEN the database is migrated, THE Web_API SHALL create a `review_job_artifact_snapshots` junction table (`review_job_id`, `artifact_id`, composite PK) recording the exact artifact set active at review-creation time, and bump `SCHEMA_VERSION` to 7.
2. WHEN `POST /api/reviews` creates a review job, THE Web_API SHALL snapshot the version's currently-active artifact IDs (from `artifact_version_links` joined on `artifacts.is_active`) into `review_job_artifact_snapshots` for that review job.
3. THE Web_API SHALL expose the snapshot via `GET /api/reviews/{review_id}/artifacts` returning the artifact IDs/titles frozen at review time, distinct from the version's current (mutable) artifact list.
4. Snapshotting SHALL NOT block or fail review creation if the version has zero active artifacts (empty snapshot is valid).

### Requirement A3 — Artifact Line Count and Content Preview

**User Story:** As a reviewer, I want to see how large an artifact is and a short preview of its content, so I can decide whether to open it without loading the full document.

#### Acceptance Criteria

1. WHEN the database is migrated to schema version 7, THE Web_API SHALL add `line_count INTEGER NOT NULL DEFAULT 0` and `content_preview TEXT NOT NULL DEFAULT ''` columns to `artifacts`.
2. WHEN an artifact is created via `POST /api/artifacts`, THE Web_API SHALL compute `line_count` as `len(content.splitlines())` and `content_preview` as the first 280 characters of `content`, and persist both.
3. THE Web_API SHALL include `line_count` and `content_preview` in `ArtifactItem`, `ArtifactResponse`, and `ArtifactInVersion` schemas and in every response that currently returns those models.
4. Existing artifacts created before this migration SHALL be backfilled with computed `line_count`/`content_preview` values from their stored `content` during the v6→v7 migration.

### Requirement A4 — Full 12-Axis Dimension Fidelity in Review Payload

**User Story:** As a reviewer, I want findings labeled with their original review dimension, not a collapsed 5-category summary, so I can see exactly which of the 12 axes flagged an issue.

#### Acceptance Criteria

1. `_build_review_payload` in `contexta/api/routers/reviews.py` SHALL set `FindingItem.type` to the original `ReviewDimensionEnum` value (e.g. `"RISK"`, `"NFR"`, `"TIMELINE"`) rather than the collapsed category.
2. THE `FindingsSummary` response model SHALL retain its existing 5-bucket counts for backward compatibility with `review_detail.py`'s summary bar, computed via the same `_DIMENSION_CATEGORY` mapping as today.
3. THIS change SHALL NOT remove `_DIMENSION_CATEGORY` — it is still needed for Requirement A4.2's summary counts.

### Requirement A5 — Full Citation Array Exposure

**User Story:** As a reviewer, I want to see every citation attached to a finding, not just the first one, so I don't lose traceability information silently.

#### Acceptance Criteria

1. `FindingItem` SHALL gain a `citations: List[CitationItem]` field (new `CitationItem` schema with `file_path`, `line_start`, `line_end`, `excerpt`) populated from the finding's full `citations` list.
2. THE existing `source_artifact`/`citation` string fields SHALL be retained and continue to be populated from `citations[0]` for backward compatibility with `finding_card.py` until Track B wires the new array.
3. IF a finding has zero citations, THEN `citations` SHALL be an empty list and `source_artifact`/`citation` SHALL fall back to their current `"unknown"`/`""` defaults.

---

### Requirement B1 — Mount Proposal Components on Version Detail Page

**User Story:** As a reviewer, I want to generate and view proposals directly from the version detail page, so I don't need a separate unlinked view.

#### Acceptance Criteria

1. `web/components/version_detail.py` SHALL import and render `proposal_form(version_id)` and `proposals_list(version_id)` from `web/components/proposal_form.py`, in a new "Proposals" section following the existing "Review Runs" section.
2. `version_detail()` SHALL call `AppState.fetch_linkable_reviews(version_id)` and `AppState.fetch_proposals_for_version(version_id)` on mount (or reuse existing on_load wiring) so both components have data without requiring a separate navigation step.

### Requirement B2 — Mount Fork Action and Dialog

**User Story:** As a reviewer, I want a visible "Fork" action in the version action bar, so I can branch a review node without using the API directly.

#### Acceptance Criteria

1. `_action_bar()` in `web/components/version_detail.py` SHALL include a "Fork" button that calls `AppState.open_fork_dialog()`.
2. A fork dialog (new `rx.dialog.root` in `version_detail.py`, bound to `AppState._fork_dialog_open`) SHALL prompt for a name via `AppState.set_fork_name`, and on confirm call `AppState.fork_node(AppState.selected_node_id, AppState._fork_name)` then close via `AppState.close_fork_dialog()`.

### Requirement B3 — Mount Scope Policy Panel

**User Story:** As a reviewer, I want to see and act on scope-modification findings directly in the review detail view, so routing decisions aren't a dead-end feature.

#### Acceptance Criteria

1. `web/components/review_detail.py` SHALL import and render `scope_policy_panel()` from `web/components/scope_policy_panel.py` inside `review_detail_pane()`, positioned after the findings list and before the proposal pane.

### Requirement B4 — Left-Pane Artifact Browser with Line/Preview Data

**User Story:** As a reviewer, I want a persistent artifact browser showing size and preview at a glance, so I can triage source documents faster.

#### Acceptance Criteria

1. `web/components/version_detail.py`'s `_artifact_row` SHALL display `line_count` (e.g. "142 lines") and a truncated `content_preview` beneath the existing title/tags row, sourced from the Track A schema fields.
2. THIS requirement depends on Requirement A3 being complete (the fields must exist in the API response) but does not require the other Track A items.

---

### Requirement C1 — Fix list[dict] Typing and Re-enable Review Link Selector

**User Story:** As a reviewer, I want to select prior reviews as context when starting a new review, so I don't lose the review-linking feature that already works end-to-end on the backend.

#### Acceptance Criteria

1. `web/pages/run_review.py` SHALL replace the disabled `rx.cond(..., rx.text("", width="0"))` placeholder with `review_link_selector(AppState.selected_version_id)` from `web/components/review_link_selector.py`.
2. `run_review_page`'s `on_load` SHALL additionally call `AppState.fetch_linkable_reviews` with the route's `version_id`, so the selector has data on page load without requiring a manual refresh.
3. THE fix SHALL resolve the underlying Reflex `list[dict]` typing issue (if it still reproduces) by ensuring `AppState.linkable_reviews` and `AppState.selected_linked_review_ids` are consumed via typed computed vars or bracket-notation access consistent with the rest of the codebase (per `triage_widget.py`'s established pattern), rather than reintroducing the original typing error.

### Requirement C2 — Insights Sidebar Wiring

**User Story:** As a reviewer, I want to see advisory insights while working on a project, so recurring risk patterns are visible without a separate admin-only view.

#### Acceptance Criteria

1. `web/components/sidebar.py` SHALL import and render `insights_sidebar()` from `web/components/insights_sidebar.py`, positioned below the projects list.
2. `web/web.py`'s `index()` `on_load` list SHALL include `AppState.fetch_insights` alongside the existing `AppState.load_projects` call.
3. THIS requirement does NOT require adding `AppState.insights` or `AppState.fetch_insights` — both already exist in `web/state.py`; only the missing render call-site and on_load wiring are in scope.

### Requirement C3 — Clickable Citation Navigation in Finding Card

**User Story:** As a reviewer, I want to click a citation and jump to the source artifact's triage entry, so I can verify a finding against its origin quickly.

#### Acceptance Criteria

1. `web/components/finding_card.py` SHALL render `finding["source_artifact"]` as an `rx.link` (or clickable element with `on_click`) instead of plain `rx.text`.
2. Clicking the citation SHALL invoke a new `AppState.navigate_to_artifact(source_artifact_path)` handler that resolves the artifact by title/path within `current_version_artifacts` and selects it (setting a new `selected_artifact_id` state var used to highlight/scroll to that row in the version detail artifact list).
3. IF the source artifact cannot be resolved (e.g. `"unknown"`), THEN the click handler SHALL show a toast (`AppState.set_toast`) indicating no matching artifact was found, rather than navigating to a broken reference.

## Non-Goals

- This spec does not implement Proactive Advisor UI (`status_banner.py` acknowledgement dialog) — that remains tracked separately per the gap-analysis Requirement 17.3 item, out of scope here.
- This spec does not change `blueprint_panel.py` / `import_panel.py` / `dream_cycle_panel.py` orphan status — those are `Fully_Implemented` via inline admin.py duplicates per the audit and are explicitly out of scope.
- Removing the version-scoped guard in `proposals.py` is explicitly rejected in favor of the additive approach in Requirement A1 — see design.md for rationale.
