# Implementation Plan: Core Scope Gaps Implementation

## Overview

Implement 11 scope gaps between the TUI specification and the web application. The work follows a vertical-slice strategy: schema → API → UI, with data model foundations (Gaps 1–2) prioritised first, then remaining gaps in numerical order. All code is Python targeting the existing aiosqlite + FastAPI + Reflex stack.

## Tasks

- [ ] 1. Database schema migration (Gaps 1–2)
  - [ ] 1.1 Add `review_links` and `proposal_review_links` tables and bump SCHEMA_VERSION to 6
    - In `contexta/db/schema.py`, add DDL for `review_links` (composite PK on `review_job_id`, `linked_review_id`, self-referencing CHECK constraint) and `proposal_review_links` (composite PK on `proposal_job_id`, `review_job_id`)
    - Bump `SCHEMA_VERSION` from 5 to 6
    - Add migration block: when `stored_version < 6`, INSERT OR IGNORE existing `proposal_jobs.review_job_id` values into `proposal_review_links`
    - _Requirements: 1.1, 2.1, 2.2_

  - [ ]* 1.2 Write property tests for schema migration
    - **Property 1: Review link insertion integrity** — verify that valid linked IDs produce correct row counts and invalid IDs produce zero rows
    - **Property 4: Proposal multi-review linking integrity** — verify junction rows match submitted review_ids
    - **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4**

- [ ] 2. Repository layer (Gaps 1–2)
  - [ ] 2.1 Implement review link repository functions
    - In `contexta/api/repositories.py`, add `ReviewLinkRow` and `ProposalReviewLinkRow` dataclasses
    - Implement `insert_review_links(conn, review_job_id, linked_ids)` — bulk-insert into `review_links`
    - Implement `get_linked_review_ids(conn, review_job_id)` — fetch all linked review IDs
    - Implement `list_linkable_reviews(conn, version_id)` — query `review_jobs` filtered by `status = 'complete'` and version
    - _Requirements: 1.2, 1.4_

  - [ ] 2.2 Implement proposal review link repository functions
    - In `contexta/api/repositories.py`, implement `insert_proposal_review_links(conn, proposal_job_id, review_ids)` — bulk-insert into `proposal_review_links`
    - Implement `list_proposals_for_version(conn, version_id)` — join `proposal_review_links` → `review_jobs` to find version-scoped proposals with linked review count
    - _Requirements: 2.3, 2.5, 11.1_

  - [ ] 2.3 Implement `update_node_metadata(conn, node_id, metadata_json)` utility
    - In `contexta/api/repositories.py`, add function to patch `metadata_json` on a node row
    - _Requirements: 5.3_

  - [ ]* 2.4 Write property tests for repository functions
    - **Property 2: Linkable reviews filter correctness** — only complete reviews returned
    - **Property 5: Version-scoped proposal listing completeness** — correct proposals with accurate linked_review_count
    - **Validates: Requirements 1.4, 2.5, 11.1**

- [ ] 3. API schemas (all gaps)
  - [ ] 3.1 Add all new Pydantic request/response models to `contexta/api/schemas.py`
    - `CreateReviewRequest` — extend with `linked_review_ids: List[str] = []`
    - `LinkableReviewItem`, `LinkableReviewsResponse`
    - `CreateVersionProposalRequest`, `ProposalListItem`, `ProposalListResponse`
    - `ForkNodeRequest`, `ForkNodeResponse`
    - `AdvisoryAlertItem`, `AcknowledgeResponse`
    - `RoutingDecisionRequest`, `RoutingDecisionResponse`
    - `ImportResponse`
    - `DreamCycleResponse`, `DreamCycleStatusResponse`
    - `BlueprintItem`, `BlueprintListResponse`, `CreateBlueprintRequest`, `BlueprintItemResponse`, `ActivateResponse`
    - `InsightItem`, `InsightsResponse`
    - `ProposalStatusResponse` — extend with `alerts: Optional[List[AdvisoryAlertItem]]`
    - _Requirements: 1.2, 1.4, 2.3, 2.5, 3.1, 4.2, 5.3, 6.1, 7.4, 8.1, 8.3, 9.1, 9.2, 10.1, 11.1_

- [ ] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Review Linking API + Pipeline Bridge (Gap 1)
  - [ ] 5.1 Extend `POST /api/reviews` to accept and validate `linked_review_ids`
    - In `contexta/api/routers/reviews.py`, add validation logic: each ID must exist in `review_jobs` with `status = 'complete'`, else return HTTP 422
    - On success, call `insert_review_links` after creating the review job
    - _Requirements: 1.2, 1.3_

  - [ ] 5.2 Add `GET /api/versions/{version_id}/reviews/linkable` endpoint
    - In `contexta/api/routers/reviews.py`, add endpoint that calls `list_linkable_reviews` and returns `LinkableReviewsResponse`
    - _Requirements: 1.4_

  - [ ] 5.3 Implement Prior Review Intelligence injection in `contexta/api/pipeline_bridge.py`
    - Add `_build_prior_intelligence(conn, review_id)` function that extracts RED/AMBER findings from linked reviews
    - Inject the formatted string into `PromptBuilder` context before launching `TaskOrchestrator`
    - _Requirements: 1.5_

  - [ ]* 5.4 Write property tests for review linking API
    - **Property 3: Prior review intelligence prompt injection** — linked review findings appear in prompt, unlinked do not
    - **Validates: Requirements 1.5**

- [ ] 6. Proposal Re-Architecture API (Gap 2 + Gap 11)
  - [ ] 6.1 Add `POST /api/versions/{version_id}/proposals` endpoint
    - In `contexta/api/routers/proposals.py`, implement version-level proposal creation: validate all `review_ids` are complete and belong to version, create `proposal_jobs` row, insert `proposal_review_links` rows, launch background task
    - Return HTTP 202 with `proposal_id` and status
    - _Requirements: 2.3, 2.4_

  - [ ] 6.2 Add `GET /api/versions/{version_id}/proposals` endpoint
    - Return list of proposals for the version via `list_proposals_for_version`, including status, creation date, progress_message, and linked_review_count
    - _Requirements: 2.5, 11.1, 11.2_

  - [ ] 6.3 Retain legacy `POST /api/proposals` as thin wrapper
    - Ensure existing endpoint delegates to the same logic with a single-element `review_ids` list
    - _Requirements: 2.6_

  - [ ]* 6.4 Write property tests for proposal architecture
    - **Property 4: Proposal multi-review linking integrity** — junction rows match submitted IDs, invalid IDs produce 422
    - **Property 5: Version-scoped proposal listing completeness** — correct proposals with accurate counts
    - **Validates: Requirements 2.3, 2.4, 2.5, 11.1**

- [ ] 7. Fork + Routing Decision + Export (Gap 3, 5, 6) — Nodes Router
  - [ ] 7.1 Create `contexta/api/routers/nodes.py` with `POST /api/nodes/{node_id}/fork`
    - Validate parent node exists (404 if missing), inherit `project_id`, `version_id`, `layer_type`
    - Create new node with `parent_id = node_id` and user-provided `name`
    - Return HTTP 201 with `ForkNodeResponse`
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 7.2 Add `POST /api/nodes/{node_id}/routing-decision` endpoint
    - Load node (404 if missing), validate `decision` field
    - If `decision == "scope_modification"` and `acknowledged != true` → HTTP 422
    - Append to `metadata_json["routing_decisions"]` list, persist via `update_node_metadata`
    - _Requirements: 5.3, 5.4, 5.5_

  - [ ] 7.3 Add `GET /api/nodes/{node_id}/export` endpoint
    - Load node (404 if missing), build JSONPacket using `JSONPacketSerializer` logic
    - Return `StreamingResponse` with `Content-Disposition: attachment` and `application/json` content type
    - Include `schema_version` field in the export payload
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 7.4 Write property tests for nodes router
    - **Property 6: Fork node inheritance** — forked node inherits parent fields correctly
    - **Property 10: Routing decision persistence** — decision appears in metadata_json
    - **Property 11: Scope modification requires explicit acknowledgement** — rejected without `acknowledged=true`
    - **Property 12: Export produces valid JSONPacket** — response validates against schema
    - **Validates: Requirements 3.1, 3.2, 5.3, 5.4, 6.1, 6.2**

- [ ] 8. Proactive Advisor Integration (Gap 4)
  - [ ] 8.1 Integrate advisor evaluation into proposal pipeline
    - In `contexta/api/pipeline_bridge.py` (or proposals router), before synthesis: load project `global_tags`, call `ProactiveAdvisor.evaluate(global_tags, conn)`
    - If alerts non-empty: store in `metadata_json`, set status to `awaiting_acknowledgement`, return early
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 8.2 Add `POST /api/proposals/{proposal_id}/acknowledge` endpoint
    - Record `acknowledged_at` ISO timestamp in `metadata_json`
    - Re-launch synthesis pipeline (which skips advisor re-evaluation after acknowledgement)
    - _Requirements: 4.4, 4.7_

  - [ ]* 8.3 Write property tests for advisor integration
    - **Property 7: Advisor alerts surface in proposal status** — all alerts appear in response
    - **Property 8: Unacknowledged alerts block synthesis** — status stays `awaiting_acknowledgement`
    - **Property 9: Acknowledgement audit trail** — valid ISO timestamp recorded
    - **Validates: Requirements 4.2, 4.3, 4.7**

- [ ] 9. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Admin Router — Import, Dream Cycle, Blueprints (Gaps 7, 8, 9)
  - [ ] 10.1 Add `POST /api/admin/import` endpoint
    - In `contexta/api/routers/admin.py`, accept multipart file upload
    - Validate against `JSONPacket` Pydantic schema — HTTP 422 if invalid, no DB write
    - On success, delegate to `JSONPacketDeserializer.import_packet()` logic, return new node ID with HTTP 201
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ] 10.2 Add Dream Cycle endpoints
    - `POST /api/admin/dream-cycle` → launch `DreamCycleWorker.run()` as BackgroundTask, return HTTP 202 (or 409 if already running)
    - `GET /api/admin/dream-cycle/status` → return current status, last_run timestamp, error if any
    - Use module-level `_dream_cycle_state` dict for state tracking
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 10.3 Add Blueprint CRUD endpoints
    - `GET /api/admin/blueprints` → list all blueprints with truncated prompt preview (200 chars)
    - `POST /api/admin/blueprints` → create new blueprint (inactive by default), return HTTP 201
    - `POST /api/admin/blueprints/{id}/activate` → set target active, deactivate all others; 404 if missing
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 10.4 Write property tests for admin endpoints
    - **Property 13: Import validation gate — round-trip safety** — invalid files rejected, valid files create nodes
    - **Property 14: Blueprint one-active invariant** — exactly one blueprint active after activation
    - **Property 15: Blueprint creation inactive by default** — new blueprints don't disturb active state
    - **Validates: Requirements 7.1, 7.2, 7.3, 9.2, 9.3**

- [ ] 11. Insights Router (Gap 10)
  - [ ] 11.1 Create `contexta/api/routers/insights.py` with `GET /api/insights`
    - Query `global_client_insights` ordered by `frequency_count DESC`, limit 10
    - Return `InsightsResponse` with `InsightItem` list (or empty list if none)
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ]* 11.2 Write property tests for insights endpoint
    - **Property 16: Insights ordering and completeness** — at most 10 entries, descending order, all fields non-null
    - **Validates: Requirements 10.1, 10.2**

- [ ] 12. Router registration and wiring
  - [ ] 12.1 Register new routers in `contexta/api/app.py`
    - Import and include `nodes.router`, `insights.router`, `admin.router` (if not already registered) with `prefix="/api"`
    - _Requirements: All (integration wiring)_

- [ ] 13. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Reflex UI — Review Linking & Proposals (Gaps 1, 2, 11)
  - [ ] 14.1 Add AppState handlers for review linking and proposals in `web/state.py`
    - `fetch_linkable_reviews(version_id)` → GET linkable endpoint, populate `linkable_reviews` state var
    - `submit_review_with_links(linked_ids)` → POST with `linked_review_ids`
    - `fetch_proposals_for_version(version_id)` → GET version proposals, populate `version_proposals` state var
    - `submit_version_proposal(review_ids)` → POST to version-level proposals endpoint
    - _Requirements: 1.6, 1.7, 2.7, 2.8, 11.3, 11.4, 11.5, 11.6_

  - [ ] 14.2 Create `web/components/review_link_selector.py`
    - Chip selector component displaying linkable reviews for user selection
    - Integrates with `submit_review_with_links` handler on form submit
    - _Requirements: 1.6, 1.7_

  - [ ] 14.3 Create `web/components/proposal_form.py`
    - Checklist of completed reviews with submit button
    - Calls `submit_version_proposal` on submit
    - Displays proposal list section with status indicators and polling for non-terminal states
    - _Requirements: 2.7, 2.8, 11.3, 11.4, 11.5, 11.6_

- [ ] 15. Reflex UI — Fork, Scope Policy, Export (Gaps 3, 5, 6)
  - [ ] 15.1 Add AppState handlers for fork, routing decisions, and export in `web/state.py`
    - `fork_node(node_id, name)` → POST fork, navigate to new node on success
    - `submit_routing_decision(node_id, finding_id, decision, acknowledged)` → POST routing-decision
    - _Requirements: 3.5, 3.6, 5.6_

  - [ ] 15.2 Create `web/components/scope_policy_panel.py`
    - Display scope-modification findings with distinct visual indicator
    - Routing toggle buttons: "Change Scope", "Route to Risk Register", "Route to Assumptions Matrix"
    - POST routing decision on selection, update visual state
    - _Requirements: 5.1, 5.2, 5.6_

  - [ ] 15.3 Add Fork button and Export button to review detail view
    - "Fork" button opens dialog for fork name, calls `fork_node` on confirm
    - "Export JSON" button triggers file download by navigating to `/api/nodes/{node_id}/export`
    - _Requirements: 3.5, 3.6, 6.5, 6.6_

- [ ] 16. Reflex UI — Admin Features (Gaps 7, 8, 9)
  - [ ] 16.1 Add AppState handlers for admin features in `web/state.py`
    - `trigger_dream_cycle()` → POST dream-cycle
    - `fetch_dream_cycle_status()` → GET status
    - `fetch_blueprints()` → GET blueprints list
    - `create_blueprint(name, version, text)` → POST create
    - `activate_blueprint(id)` → POST activate
    - `acknowledge_proposal(proposal_id)` → POST acknowledge
    - _Requirements: 4.5, 4.6, 8.6, 8.7, 9.5, 9.6, 9.7_

  - [ ] 16.2 Create `web/components/dream_cycle_panel.py`
    - "Run Dream Cycle" button, disabled while running
    - Status indicator showing idle/running/complete/failed and last run timestamp
    - _Requirements: 8.6, 8.7_

  - [ ] 16.3 Create `web/components/blueprint_panel.py`
    - DataTable listing blueprints (name, version, active status)
    - Create form with name, version_string, prompt_text fields
    - "Activate" action button on non-active rows
    - _Requirements: 9.5, 9.6, 9.7_

  - [ ] 16.4 Create `web/components/import_panel.py`
    - File upload component in "Import" section of Admin page
    - POST file to `/api/admin/import`, display success/error toast
    - _Requirements: 7.5, 7.6_

- [ ] 17. Reflex UI — Insights Sidebar + Advisor Dialog (Gaps 4, 10)
  - [ ] 17.1 Add AppState handler for insights in `web/state.py`
    - `fetch_insights()` → GET insights, populate `insights` state var
    - Refresh on navigation to project/version detail
    - _Requirements: 10.4, 10.5, 10.6_

  - [ ] 17.2 Create `web/components/insights_sidebar.py`
    - Collapsible sidebar section with advisory cards (tag, pattern, frequency)
    - Badge on header showing insight count
    - _Requirements: 10.4, 10.5_

  - [ ] 17.3 Add advisor acknowledgement dialog to proposal views
    - Blocking confirmation dialog when proposal enters `awaiting_acknowledgement`
    - Shows all detected alerts, calls `acknowledge_proposal` on confirm
    - _Requirements: 4.5, 4.6_

- [ ] 18. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Priority ordering: Gaps 1–2 (data model) first, then remaining in numerical order
- All new DDL goes in `contexta/db/schema.py`, repository functions in `contexta/api/repositories.py`
- Existing working modules to integrate: `pipeline/advisor.py`, `pipeline/scope_policy.py`, `admin/dream_cycle.py`, `admin/blueprint_manager.py`, `export/serializer.py`, `export/deserializer.py`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "2.2", "2.3"] },
    { "id": 2, "tasks": ["2.4", "5.1", "5.2", "5.3"] },
    { "id": 3, "tasks": ["5.4", "6.1", "6.2", "6.3"] },
    { "id": 4, "tasks": ["6.4", "7.1", "7.2", "7.3"] },
    { "id": 5, "tasks": ["7.4", "8.1", "8.2"] },
    { "id": 6, "tasks": ["8.3", "10.1", "10.2", "10.3", "11.1"] },
    { "id": 7, "tasks": ["10.4", "11.2", "12.1"] },
    { "id": 8, "tasks": ["14.1", "15.1", "16.1", "17.1"] },
    { "id": 9, "tasks": ["14.2", "14.3", "15.2", "15.3"] },
    { "id": 10, "tasks": ["16.2", "16.3", "16.4", "17.2", "17.3"] }
  ]
}
```
