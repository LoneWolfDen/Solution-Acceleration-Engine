# Implementation Plan: Gap Remediation Phase 2 (Parallel Tracks)

## Overview

Three isolated, parallelizable tracks closing the remaining items from `.kiro/specs/review-implementation-gaps/gap-analysis.md`. File ownership is disjoint per track (see design.md) so three agents can execute simultaneously without merge conflicts. Track A should land first if strict sequencing is required, since B and C read Track A's new response fields — but B/C tasks are written to be implementable against the documented contract in requirements.md without blocking on A's merge.

Note on scope correction: Track A does **not** remove the `WHERE rj.version_id = ?` guard in `contexta/api/routers/proposals.py`. That guard is the tested, intentional Gap 2/11 implementation. Instead, Track A adds an additive project-scope endpoint. See design.md "Key Design Decision" for the full rationale.

---

## Track A — Backend: Schema, Provenance, Payload Fidelity

- [ ] A1. Schema migration to v7
  - [ ] A1.1 Add `line_count`, `content_preview` columns to `artifacts` and new `review_job_artifact_snapshots` table
    - In `contexta/db/schema.py`: bump `SCHEMA_VERSION` to 7; add the two `ALTER TABLE artifacts ADD COLUMN` statements and the `CREATE TABLE IF NOT EXISTS review_job_artifact_snapshots (...)` DDL (composite PK on `review_job_id`, `artifact_id`) to `DDL_STATEMENTS`
    - In `run_migrations()`, add a `stored_version < 7` migration block that: (a) runs the two `ALTER TABLE` statements guarded by try/except (idempotent on fresh installs, same pattern as the existing v1→v2 block), (b) backfills `line_count = LENGTH(content) - LENGTH(REPLACE(content, char(10), '')) + 1` and `content_preview = SUBSTR(content, 1, 280)` for all existing rows via a single `UPDATE artifacts SET ...` statement
    - _Requirements: A3.1, A3.4_
  - [ ] A1.2 Add `review_links`-style DDL test coverage for the new table
    - New file `tests/test_schema_migration_v7.py`: assert `SCHEMA_VERSION == 7`, assert `review_job_artifact_snapshots` table exists after `init_database()`, assert `artifacts` table has `line_count`/`content_preview` columns via `PRAGMA table_info(artifacts)`, assert re-running `run_migrations()` on an already-migrated connection is a no-op (idempotency)
    - _Requirements: A3.1, A3.4_

- [ ] A2. Artifact line-count/preview population
  - [ ] A2.1 Compute and persist `line_count`/`content_preview` on artifact creation
    - In `contexta/api/repositories.py`: add `line_count: int = 0` and `content_preview: str = ""` fields to `ArtifactRow`; update `_row_to_artifact()` to read both columns; update `create_artifact()` to compute `line_count = len(content.splitlines())` and `content_preview = content[:280]` and include them in the `INSERT` statement
    - _Requirements: A3.2_
  - [ ] A2.2 Expose the new fields on every artifact response schema
    - In `contexta/api/schemas.py`: add `line_count: int = 0` and `content_preview: str = ""` to `ArtifactItem`, `ArtifactResponse`, and `ArtifactInVersion`
    - In `contexta/api/routers/artifacts.py`: pass `line_count=a.line_count, content_preview=a.content_preview` in `list_artifacts()` and `create_artifact()`'s response construction; same for `update_artifact_active()`
    - Find and update wherever `ArtifactInVersion` is constructed (version detail endpoint in `contexta/api/routers/versions.py`) to include the two new fields
    - _Requirements: A3.3_
  - [ ] A2.3 Unit tests for line-count/preview computation
    - New tests in `tests/api/test_artifacts.py`: POST an artifact with known multi-line content, assert `line_count` matches `content.count("\n") + 1` and `content_preview` matches the first 280 chars; test empty-content edge case (`line_count == 1` for empty string per `splitlines()` semantics — assert the exact chosen convention); test content shorter than 280 chars (preview equals full content)
    - _Requirements: A3.2_

- [ ] A3. Review-run artifact snapshot provenance
  - [ ] A3.1 Snapshot active artifacts at review creation time
    - In `contexta/api/repositories.py`: add `insert_review_job_artifact_snapshot(conn, review_job_id, artifact_ids)` (bulk insert into `review_job_artifact_snapshots`) and `get_review_job_artifact_snapshot(conn, review_job_id)` (returns joined artifact rows: id, title, tags)
    - In `contexta/api/routers/reviews.py`'s `create_review()`: after `create_review_job()`, query `artifact_version_links` joined on `artifacts.is_active = 1` for `body.version_id`, and call `insert_review_job_artifact_snapshot()` with the resulting artifact IDs before launching the background task
    - _Requirements: A2.2, A2.4_
  - [ ] A3.2 Expose the snapshot endpoint
    - In `contexta/api/schemas.py`: add `ReviewArtifactSnapshotItem` (`artifact_id`, `title`, `tags`) and `ReviewArtifactSnapshotResponse` (`artifacts: List[ReviewArtifactSnapshotItem]`)
    - In `contexta/api/routers/reviews.py`: add `GET /reviews/{review_id}/artifacts` returning the snapshot via `get_review_job_artifact_snapshot()`; 404 if the review job doesn't exist
    - _Requirements: A2.3_
  - [ ] A3.3 Tests for snapshot provenance
    - New file `tests/api/test_review_snapshots.py`: create a version with 2 active + 1 inactive artifact, POST a review, assert `GET /reviews/{id}/artifacts` returns exactly the 2 active artifacts; then deactivate one of the originally-active artifacts and re-fetch the snapshot, asserting it still shows the original 2 (proving immutability against later mutation); test zero-active-artifact case returns an empty list without error
    - _Requirements: A2.2, A2.3, A2.4_

- [ ] A4. Project-scoped proposal aggregation (additive)
  - [ ] A4.1 Add `version_id` to proposal listing and a new project-level repository function
    - In `contexta/api/repositories.py`: add `version_id: str` field to `ProposalListItem`; update the SQL in `list_proposals_for_version()` to also select/return `review_jobs.version_id`; add new `list_proposals_for_project(conn, project_id)` joining `proposal_review_links` → `review_jobs` → `versions` filtered by `versions.project_id = ?`, returning the same `ProposalListItem` shape across all versions
    - _Requirements: A1.1, A1.3_
  - [ ] A4.2 Add the new endpoint without touching existing ones
    - In `contexta/api/schemas.py`: add `version_id: str` to `ProposalListItem`
    - In `contexta/api/routers/proposals.py`: add `GET /projects/{project_id}/proposals` calling `list_proposals_for_project()`; 404 if project doesn't exist (reuse `db_repo.get_project`); do NOT modify `create_version_proposal`, `list_version_proposals`, `_create_version_proposal`, or their existing validation/422 guards
    - Register no new router — `proposals.router` already handles this path prefix once mounted under `/api`
    - _Requirements: A1.1, A1.2, A1.4_
  - [ ] A4.3 Tests proving additive-only change
    - New tests in `tests/api/test_proposals.py`: `test_project_scoped_proposals_aggregates_across_versions` (2 versions, 1 proposal each, assert both appear via the project endpoint with correct `version_id`); `test_project_scoped_proposals_unknown_project_404`; re-run the full existing test file and confirm no existing test needed modification (this is a regression guard, not new coverage — call out explicitly in the PR description)
    - _Requirements: A1.1, A1.2, A1.4_

- [ ] A5. 12-axis dimension fidelity + full citation array
  - [ ] A5.1 Add `CitationItem` schema and populate full citation arrays
    - In `contexta/api/schemas.py`: add `CitationItem` (`file_path: str`, `line_start: int`, `line_end: int`, `excerpt: str`); add `citations: List[CitationItem] = []` to `FindingItem`
    - In `contexta/api/routers/reviews.py`'s `_build_review_payload()`: for each finding, build `citations=[schemas.CitationItem(file_path=c.file_path, line_start=c.line_start, line_end=c.line_end, excerpt=c.excerpt) for c in f.citations]` in addition to the existing `source_artifact`/`citation` (kept as-is, sourced from `citations[0]`, for backward compat)
    - _Requirements: A5.1, A5.2, A5.3_
  - [ ] A5.2 Expose original dimension label on FindingItem.type
    - In `contexta/api/routers/reviews.py`'s `_build_review_payload()`: change `type=f.dimension.value` is already the raw enum value being passed — verify current behavior; if `type` is currently the raw dimension (it already reads `f.dimension.value`), this task instead confirms via test that all 12 `ReviewDimensionEnum` values round-trip correctly and that `summary_counts` (5-bucket) is unaffected by this confirmation
    - _Requirements: A4.1, A4.2, A4.3_
  - [ ] A5.3 Tests for dimension fidelity and citation array
    - New tests in `tests/api/test_reviews.py`: construct a node with findings spanning all 12 `ReviewDimensionEnum` values, assert `GET /nodes/{id}` returns each `FindingItem.type` as the exact original enum value (not a collapsed category) and that `summary` counts still sum correctly per the 5-bucket mapping; construct a finding with 3 citations, assert `citations` array has all 3 entries while `citation`/`source_artifact` reflect only the first
    - _Requirements: A4.1, A4.2, A5.1, A5.2, A5.3_

- [ ] A6. Checkpoint — Track A backend verification
  - Run `pytest tests/api/ tests/test_schema_migration_v7.py -v` and confirm all pass, including the full pre-existing `tests/api/test_proposals.py` suite unmodified in behavior. Ask the user if anything is ambiguous before Track B/C consume these contracts.

---

## Track B — Frontend Views: Mount Orphaned Components

- [ ] B1. Mount proposal components on version detail page
  - [ ] B1.1 Import and render `proposal_form`/`proposals_list` in `version_detail.py`
    - In `web/components/version_detail.py`: add `from web.components.proposal_form import proposal_form, proposals_list`; add a new `rx.vstack` "Proposals" section (using the same `_section_label("sparkles", "Proposals")` pattern as existing sections) after the "Review Runs" section, rendering `proposal_form(version["id"].to(str))` and `proposals_list(version["id"].to(str))`
    - _Requirements: B1.1_
  - [ ] B1.2 Wire data fetch on version selection
    - Confirm whether `AppState.select_version()` in `web/state.py` needs a call to `fetch_linkable_reviews`/`fetch_proposals_for_version` — if Track C or existing code doesn't already trigger these on version select, add calls inside `version_detail()`'s render via `rx.fragment(rx.script(...))`-free approach: prefer adding the two calls to `AppState.select_version()`'s existing `yield` flow in `web/state.py` (cross-track note: coordinate with Track C owner if both tracks touch `state.py`; if avoided, use `on_mount` on the "Proposals" section box instead)
    - _Requirements: B1.2_

- [ ] B2. Mount fork action and dialog
  - [ ] B2.1 Add "Fork" button to the action bar
    - In `web/components/version_detail.py`'s `_action_bar()`: add a third button "Fork" with `rx.icon("git-fork", size=13)`, `on_click=AppState.open_fork_dialog`
    - _Requirements: B2.1_
  - [ ] B2.2 Add the fork dialog
    - In `web/components/version_detail.py`: add a new `_fork_dialog()` function returning `rx.dialog.root(...)` bound to `open=AppState._fork_dialog_open`, containing an `rx.input` bound to `value=AppState._fork_name, on_change=AppState.set_fork_name`, and Cancel/Confirm buttons calling `AppState.close_fork_dialog` and `AppState.fork_node(AppState.selected_node_id, AppState._fork_name)` respectively; render `_fork_dialog()` once at the top level of `version_detail()`
    - _Requirements: B2.2_

- [ ] B3. Mount scope policy panel
  - [ ] B3.1 Import and render `scope_policy_panel` in review detail
    - In `web/components/review_detail.py`: add `from web.components.scope_policy_panel import scope_policy_panel`; render `scope_policy_panel()` inside `review_detail_pane()` between the findings `rx.cond` block and `rx.separator(width="100%")` (before `_proposal_pane()`)
    - _Requirements: B3.1_

- [ ] B4. Artifact browser line-count/preview display
  - [ ] B4.1 Extend `_artifact_row` with size/preview info
    - In `web/components/version_detail.py`'s `_artifact_row()`: below the title/tags row, add `rx.text(artifact["line_count"].to(str) + " lines", size="1", color_scheme="gray")` and `rx.text(artifact["content_preview"].to(str), size="1", color_scheme="gray", truncate=True)` — depends on Track A's A2.2 response fields existing; if A hasn't merged yet, stub with `artifact.get("line_count", 0)`-equivalent bracket-safe default per the codebase's established `.to(list[str])` pattern
    - _Requirements: B4.1, B4.2_

- [ ] B5. Checkpoint — Track B verification
  - Run `python -c "import web.web"` to confirm all new imports resolve without circular import or syntax errors; manually start `reflex run` (user-run, not background) and visually confirm the Proposals section, Fork dialog, and Scope Policy panel render without console errors. Ask the user if any Reflex compile error appears — do not guess at Reflex-specific fixes without checking the reflex-docs skill if installed.

---

## Track C — Frontend State: Typing Fix + Missing Wiring

- [ ] C1. Fix review link selector wiring in run_review.py
  - [ ] C1.1 Replace the disabled placeholder with the real component
    - In `web/pages/run_review.py`: add `from web.components.review_link_selector import review_link_selector`; replace the `rx.cond(AppState.selected_version_id != "", rx.text("", width="0"))` block with `rx.cond(AppState.selected_version_id != "", review_link_selector(AppState.selected_version_id))`
    - _Requirements: C1.1_
  - [ ] C1.2 Fetch linkable reviews on page load
    - In `web/pages/run_review.py`: add `AppState.fetch_linkable_reviews` to the `on_load` list of the `rx.page(...)` decorator — note this needs the `version_id` route param; if `fetch_linkable_reviews` needs an argument and `on_load` handlers can't easily pass route params inline, add a small wrapper in `web/state.py`: `async def load_run_review_linkable(self): await self.fetch_linkable_reviews(self.version_id)`, and reference that wrapper in `on_load` instead
    - _Requirements: C1.2_
  - [ ] C1.3 Verify no residual list[dict] typing error
    - Confirm `AppState.linkable_reviews` (`list[dict]`) is consumed in `review_link_selector.py` exclusively via bracket notation (`review["review_id"]`) inside `rx.foreach` callbacks, matching the working pattern already used in `triage_widget.py`/`proposal_form.py`'s `_review_checkbox`. If `reflex run` still raises a typing error after C1.1, capture the exact error and adjust the offending Var access pattern rather than re-disabling the block
    - _Requirements: C1.3_

- [ ] C2. Wire insights sidebar
  - [ ] C2.1 Render `insights_sidebar()` in the sidebar
    - In `web/components/sidebar.py`: add `from web.components.insights_sidebar import insights_sidebar`; render `insights_sidebar()` inside `sidebar()`'s `rx.vstack`, positioned after the scroll_area of projects (as a fixed-height footer section) — do not modify `AppState`, both `insights` and `fetch_insights` already exist
    - _Requirements: C2.1_
  - [ ] C2.2 Fetch insights on initial page load
    - In `web/web.py`: change `on_load=AppState.load_projects` on `app.add_page(index, ...)` to `on_load=[AppState.load_projects, AppState.fetch_insights]`
    - _Requirements: C2.2_

- [ ] C3. Clickable citation navigation
  - [ ] C3.1 Add `navigate_to_artifact` handler and `selected_artifact_id` state
    - In `web/state.py`: add `selected_artifact_id: str = ""` state var; add `def navigate_to_artifact(self, source_artifact: str) -> None` that searches `self.current_version_artifacts` for a matching `title` (or path) field, sets `self.selected_artifact_id` to the match's `artifact_id` if found, and calls `self.set_toast("No matching artifact found for this citation.", is_error=True)` if not found — this is a plain synchronous method, unit-testable without httpx
    - _Requirements: C3.2, C3.3_
  - [ ] C3.2 Make the citation clickable in finding_card.py
    - In `web/components/finding_card.py`: wrap the `rx.text(finding["source_artifact"], ...)` in Row 1 with `rx.link(..., on_click=AppState.navigate_to_artifact(finding["source_artifact"]), cursor="pointer", color_scheme="indigo")` (or use `rx.box` with `on_click` if `rx.link` styling conflicts with the existing monospace/truncate styling — preserve existing size/truncate/max_width props)
    - _Requirements: C3.1_
  - [ ] C3.3 Highlight the resolved artifact in version_detail.py
    - In `web/components/version_detail.py`'s `_artifact_row()`: add a highlight condition `is_highlighted = AppState.selected_artifact_id == artifact["artifact_id"]` and apply a distinct `border_color`/`background` when true (same visual pattern already used for `is_selected` in `_review_row`/`_node_row`) — cross-track note: this touches a file Track B also owns; coordinate merge order or apply as a small isolated diff to avoid conflicts
    - _Requirements: C3.2_
  - [ ] C3.4 Unit test for artifact resolution logic
    - New file `tests/test_navigate_to_artifact.py`: instantiate `AppState` (or test the resolution logic extracted as a pure function if instantiating `rx.State` directly in a test is impractical — check existing precedent in `tests/test_ui_integration.py` first), set `selected_version` with known artifacts, call `navigate_to_artifact` with a matching and a non-matching title, assert `selected_artifact_id` and `toast_message`/`toast_is_error` behave per Requirement C3.3
    - _Requirements: C3.1, C3.2, C3.3_

- [ ] C4. Checkpoint — Track C verification
  - Run `python -c "import web.web"` and `pytest tests/test_navigate_to_artifact.py -v`. Manually verify (user-run `reflex run`) that the review-link selector renders on `/run-review/[version_id]` without a Reflex compile-time typing error, insights sidebar appears under the project list, and clicking a citation highlights the right artifact row. Ask the user if the typing issue reproduces in a form not covered by C1.3.

---

## Cross-Track Coordination Notes

- Tracks B and C both list `version_detail.py` as a touch point in B4/C3.3. If run truly in parallel by separate agents, whichever merges second must rebase the artifact-row diff rather than overwrite it. Recommend running B and C sequentially on this one file, or assigning `_artifact_row` changes to a single owner.
- Track B's B1.2 and Track C's `state.py` edits (C2.1 has none, C3.1 does) both touch `web/state.py`. C3.1 only *adds* a new var and method; B1.2 only *adds* calls inside an existing method. These are additive and low-conflict but should still be merged one at a time with a re-read of the file before the second edit.
- No task in any track modifies `contexta/api/routers/proposals.py`'s existing guarded logic — this is intentional and should not be "fixed" by any agent noticing the version-scoping during implementation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["A1.1", "A2.1", "C1.1", "C2.1", "B3.1"] },
    { "id": 1, "tasks": ["A1.2", "A2.2", "A3.1", "A4.1", "A5.1", "C1.2", "C2.2", "B1.1", "B2.1", "B2.2"] },
    { "id": 2, "tasks": ["A2.3", "A3.2", "A4.2", "A5.2", "C1.3", "C3.1", "B1.2"] },
    { "id": 3, "tasks": ["A3.3", "A4.3", "A5.3", "C3.2", "B4.1"] },
    { "id": 4, "tasks": ["A6", "C3.3"] },
    { "id": 5, "tasks": ["C3.4", "B5", "C4"] }
  ]
}
```

## Notes

- Every task's file paths are the ground truth taken from direct inspection of the current codebase at planning time (not the original gap-analysis.md, which was already partly stale for Track C's insights item — `AppState.insights`/`fetch_insights` already exist, contrary to the audit's "would error if ever rendered" note).
- No task removes or weakens the existing version-scoped proposal validation — see design.md.
- Track A tests follow the existing `tests/api/test_*.py` convention (see `test_proposals.py`, `test_artifacts.py`) rather than introducing a new test layout.
