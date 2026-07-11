# Requirements Document

## Introduction

This document specifies the 11 scope gaps identified between the original Project Contexta design and the current web application implementation. Each gap represents a feature that exists in the TUI specification but has no corresponding implementation in the Web UI or REST API layer. The implementation follows a vertical-slice strategy: schema → API → UI delivered sequentially, with data model foundations (Gaps 1–2) prioritised first.

All features build on the existing aiosqlite async data layer, LiteLLM temperature=0.0 JSON-mode inference, Reflex frontend, and FastAPI backend. DDL migrations are idempotent. All changes are backward compatible with the existing API surface.

---

## Glossary

- **Web_API**: The FastAPI-based REST API layer serving the Reflex frontend at `/api/*`.
- **Reflex_UI**: The Reflex-based frontend application rendering the web interface.
- **Review_Job**: A row in the `review_jobs` table tracking an async review pipeline run.
- **Proposal_Job**: A row in the `proposal_jobs` table tracking an async synthesis pipeline run.
- **Review_Link**: A junction record in `review_links` associating a Review_Job with one or more prior Review_Jobs as context.
- **Proposal_Review_Link**: A junction record in `proposal_review_links` associating a Proposal_Job with one or more Review_Jobs as synthesis sources.
- **Version_Detail_Page**: The Reflex UI page at `/run-review/{version_id}` displaying version artifacts, reviews, and proposals.
- **Admin_Page**: The Reflex UI page at `/admin` displaying system configuration, blueprints, and operational controls.
- **JSONPacket**: A flat structured JSON export of the full pipeline state for a given node, including schema_version, ReviewNodePayload objects, routing decisions, and metadata.
- **Proactive_Advisor**: The Layer 2 engine that evaluates global tag combinations and emits blocking advisory alerts for high-risk patterns.
- **Dream_Cycle**: A background worker that analyses the global database and updates `global_client_insights`.
- **Blueprint**: A versioned master prompt stored in `prompt_blueprints`, used to drive dimension review and synthesis LLM calls.
- **Scope_Policy**: The enforcement rule that prevents direct scope modification, routing changes instead to Risk Register or Assumptions Matrix.
- **Fork**: The act of creating a new Node branched from an existing Node under the same project, preserving lineage via `parent_id`.
- **Global_Client_Insights**: Aggregated pattern data stored in `global_client_insights`, surfaced as advisory hints in the UI sidebar.
- **Linkable_Review**: A completed Review_Job eligible to be linked as prior context for a new review.
- **Routing_Decision**: A user determination on how to handle a scope-modification finding: route to Risk Register, Assumptions Matrix, or approve scope change.

---

## Requirements

### Requirement 1 — Review Linking (Gap 1)

**User Story:** As a reviewer, I want to link prior completed reviews as context for a new review so that the LLM prompt includes prior intelligence and produces more informed findings.

#### Acceptance Criteria

1. WHEN the database is initialised or migrated, THE Web_API SHALL create a `review_links` junction table with columns `review_job_id` (FK → review_jobs.id) and `linked_review_id` (FK → review_jobs.id) with a composite primary key on both columns.
2. WHEN a POST request is received at `/api/reviews` with a `linked_review_ids` field, THE Web_API SHALL insert one row into `review_links` for each provided linked review ID associated with the newly created Review_Job.
3. IF any value in `linked_review_ids` does not correspond to an existing completed Review_Job, THEN THE Web_API SHALL return HTTP 422 with a message identifying the invalid review ID.
4. WHEN a GET request is received at `/api/versions/{version_id}/reviews/linkable`, THE Web_API SHALL return a list of all completed Review_Jobs for that version eligible for linking (status = 'complete').
5. WHEN a review pipeline task runs for a Review_Job with linked reviews, THE Web_API SHALL inject the findings from all linked reviews into the LLM prompt as Prior Review Intelligence context.
6. THE Reflex_UI SHALL display a chip selector component on the Version_Detail_Page allowing users to select prior reviews before triggering a new review.
7. WHEN the user submits a new review with linked reviews selected, THE Reflex_UI SHALL include the selected review IDs in the `linked_review_ids` field of the POST request body.

---

### Requirement 2 — Proposal Re-Architecture (Gap 2)

**User Story:** As a reviewer, I want to generate proposals from multiple completed reviews so that the synthesis reflects a broader analysis scope rather than a single review run.

#### Acceptance Criteria

1. WHEN the database is initialised or migrated, THE Web_API SHALL create a `proposal_review_links` junction table with columns `proposal_job_id` (FK → proposal_jobs.id) and `review_job_id` (FK → review_jobs.id) with a composite primary key on both columns.
2. WHEN the database is migrated, THE Web_API SHALL execute a data migration copying each existing `proposal_jobs.review_job_id` value into `proposal_review_links` as a single-row link, preserving backward compatibility.
3. WHEN a POST request is received at `/api/versions/{version_id}/proposals` with a `review_ids` list, THE Web_API SHALL create a new Proposal_Job and insert one row into `proposal_review_links` for each provided review ID.
4. IF any value in `review_ids` does not correspond to a completed Review_Job for the specified version, THEN THE Web_API SHALL return HTTP 422 with a message identifying the invalid review ID.
5. WHEN a GET request is received at `/api/versions/{version_id}/proposals`, THE Web_API SHALL return a list of all Proposal_Jobs associated with reviews belonging to that version, including status, creation date, and linked review count.
6. THE Web_API SHALL retain the legacy POST `/api/proposals` endpoint as a thin wrapper that creates a single-review proposal using the existing `review_id` field, delegating to the same underlying logic.
7. THE Reflex_UI SHALL display a "Generate Proposal" section on the Version_Detail_Page with a checklist of completed reviews for user selection.
8. WHEN the user submits the proposal form with selected reviews, THE Reflex_UI SHALL POST to `/api/versions/{version_id}/proposals` with the selected review IDs.

---

### Requirement 3 — Fork Iteration via Web (Gap 3)

**User Story:** As a reviewer, I want to fork a review node into a versioned branch via the web interface so that I can explore alternative review paths without overwriting original findings.

#### Acceptance Criteria

1. WHEN a POST request is received at `/api/nodes/{node_id}/fork` with a `name` field, THE Web_API SHALL create a new Node in the `nodes` table with `parent_id` set to the specified node_id and `node_name` set to the provided name.
2. THE newly forked Node SHALL inherit the `project_id`, `version_id`, and `layer_type` of the parent Node.
3. IF the specified node_id does not exist, THEN THE Web_API SHALL return HTTP 404 with a descriptive message.
4. WHEN the fork completes successfully, THE Web_API SHALL return the new Node's ID, name, and creation timestamp with HTTP 201.
5. THE Reflex_UI SHALL display a "Fork" button in the review detail view that opens a dialog prompting for a fork name.
6. WHEN the user confirms the fork dialog, THE Reflex_UI SHALL POST to `/api/nodes/{node_id}/fork` and navigate to the newly created node upon success.

---

### Requirement 4 — Proactive Advisor Integration (Gap 4)

**User Story:** As a reviewer, I want the system to warn me about high-risk tag patterns during proposal synthesis so that I can acknowledge known risks before proceeding.

#### Acceptance Criteria

1. WHEN the proposal synthesis pipeline task begins, THE Web_API SHALL invoke the Proactive_Advisor evaluation against the project's `global_tags` and `global_client_insights`.
2. WHEN the Proactive_Advisor detects a high-risk tag combination, THE Web_API SHALL include an `alerts` array in the proposal status response containing the detected pattern, frequency count, and advisory text.
3. WHILE a proposal has unacknowledged alerts, THE Web_API SHALL set the proposal status to `awaiting_acknowledgement` instead of proceeding to synthesis.
4. WHEN a POST request is received at `/api/proposals/{proposal_id}/acknowledge`, THE Web_API SHALL record the acknowledgement in the Proposal_Job metadata and resume synthesis.
5. THE Reflex_UI SHALL display a blocking confirmation dialog when a proposal enters `awaiting_acknowledgement` status, showing all detected alerts.
6. WHEN the user confirms the dialog, THE Reflex_UI SHALL POST the acknowledgement and resume polling for synthesis completion.
7. THE Web_API SHALL record each acknowledgement with a timestamp in the Proposal_Job's metadata_json for audit purposes.

---

### Requirement 5 — Scope Policy Enforcement UI (Gap 5)

**User Story:** As a reviewer, I want to see routing options for scope-modification findings in the web interface so that I can direct scope changes to Risk Register or Assumptions Matrix instead of silently accepting them.

#### Acceptance Criteria

1. WHEN a completed review contains findings with `mitigation_routing = 'Scope Modification'`, THE Reflex_UI SHALL highlight those findings with a distinct visual indicator in the review detail view.
2. THE Reflex_UI SHALL display routing toggle buttons for each scope-modification finding offering three options: "Change Scope", "Route to Risk Register", and "Route to Assumptions Matrix".
3. WHEN a POST request is received at `/api/nodes/{node_id}/routing-decision` with fields `finding_id` and `decision`, THE Web_API SHALL update the node's `metadata_json` to record the routing decision for that finding.
4. IF the `decision` value is "scope_modification", THEN THE Web_API SHALL require an `acknowledged` boolean field set to true, confirming explicit scope change approval.
5. IF the specified node_id does not exist, THEN THE Web_API SHALL return HTTP 404.
6. WHEN the user selects a routing option in the UI, THE Reflex_UI SHALL POST to `/api/nodes/{node_id}/routing-decision` and update the finding's visual state to reflect the recorded decision.

---

### Requirement 6 — JSON Export via Web (Gap 6)

**User Story:** As a reviewer, I want to export the full pipeline state for a review node as a downloadable JSON file from the web interface so that I can share or archive review output portably.

#### Acceptance Criteria

1. WHEN a GET request is received at `/api/nodes/{node_id}/export`, THE Web_API SHALL serialise the node's complete pipeline state — including all ReviewNodePayload objects, synthesis output, routing decisions, and metadata_json — into a JSONPacket.
2. THE exported JSONPacket SHALL include a `schema_version` field identifying the Contexta data schema version used.
3. THE Web_API SHALL return the JSONPacket with `Content-Disposition: attachment; filename="{node_name}_{node_id}.json"` and content type `application/json`.
4. IF the specified node_id does not exist, THEN THE Web_API SHALL return HTTP 404.
5. THE Reflex_UI SHALL display an "Export JSON" button in the review detail view.
6. WHEN the user clicks the "Export JSON" button, THE Reflex_UI SHALL trigger a file download by navigating to the export endpoint URL.

---

### Requirement 7 — JSON Import via Web (Gap 7)

**User Story:** As an administrator, I want to import a previously exported JSONPacket via the web interface so that I can restore or migrate pipeline state without terminal access.

#### Acceptance Criteria

1. WHEN a POST request with a multipart file upload is received at `/api/admin/import`, THE Web_API SHALL read the uploaded file and attempt to parse it as a JSONPacket.
2. THE Web_API SHALL validate the uploaded JSONPacket against the current ReviewNodePayload and Node schemas before writing any data to the database.
3. IF the uploaded file fails schema validation, THEN THE Web_API SHALL return HTTP 422 with validation error details and SHALL NOT write any data to the database.
4. WHEN a valid JSONPacket is imported successfully, THE Web_API SHALL create a new Node in the `nodes` table representing the imported state and return the new Node ID with HTTP 201.
5. THE Reflex_UI SHALL display a file upload component on the Admin_Page within an "Import" section.
6. WHEN the user uploads a file and submits, THE Reflex_UI SHALL POST the file to `/api/admin/import` and display a success or error toast based on the response.

---

### Requirement 8 — Dream Cycle Web Integration (Gap 8)

**User Story:** As an administrator, I want to trigger and monitor the Dream Cycle background analysis from the web interface so that I can update advisory insights without terminal access.

#### Acceptance Criteria

1. WHEN a POST request is received at `/api/admin/dream-cycle`, THE Web_API SHALL launch the Dream Cycle background worker and return HTTP 202 with a `job_id` and status `running`.
2. IF a Dream Cycle is already running when a new trigger is received, THEN THE Web_API SHALL return HTTP 409 with a message indicating a cycle is already in progress.
3. WHEN a GET request is received at `/api/admin/dream-cycle/status`, THE Web_API SHALL return the current Dream Cycle status (idle, running, complete, or failed) and the timestamp of the last completed run.
4. WHEN the Dream Cycle worker completes successfully, THE Web_API SHALL update the `global_client_insights` table with newly identified or updated patterns.
5. IF the Dream Cycle worker encounters an error, THEN THE Web_API SHALL record the error in the status response and terminate the worker without corrupting the `global_client_insights` table.
6. THE Reflex_UI SHALL display a "Run Dream Cycle" button on the Admin_Page.
7. WHILE the Dream Cycle is running, THE Reflex_UI SHALL display a status indicator showing the worker is active and disable the trigger button.

---

### Requirement 9 — Blueprint Management Web UI (Gap 9)

**User Story:** As an administrator, I want to manage prompt blueprints from the web interface so that I can create, view, and activate blueprints without terminal access.

#### Acceptance Criteria

1. WHEN a GET request is received at `/api/admin/blueprints`, THE Web_API SHALL return a list of all records in `prompt_blueprints` including id, name, version_string, is_active status, and a truncated preview of the prompt text.
2. WHEN a POST request is received at `/api/admin/blueprints` with fields `name`, `version_string`, and `prompt_text`, THE Web_API SHALL create a new blueprint record and return it with HTTP 201.
3. WHEN a POST request is received at `/api/admin/blueprints/{id}/activate`, THE Web_API SHALL set `is_active = true` for the specified blueprint and `is_active = false` for all other blueprints.
4. IF the specified blueprint id does not exist, THEN THE Web_API SHALL return HTTP 404.
5. THE Reflex_UI SHALL display a Blueprint panel on the Admin_Page with a DataTable listing all blueprints, showing name, version, and active status.
6. THE Reflex_UI SHALL provide a form to create a new blueprint with name, version, and prompt text fields.
7. THE Reflex_UI SHALL provide an "Activate" action button on each non-active blueprint row in the DataTable.

---

### Requirement 10 — Global Client Insights Sidebar (Gap 10)

**User Story:** As a reviewer, I want to see top advisory hints derived from global client insights in a sidebar so that recurring failure patterns inform my review decisions.

#### Acceptance Criteria

1. WHEN a GET request is received at `/api/insights`, THE Web_API SHALL return the top advisory hints from `global_client_insights` ordered by `frequency_count` descending, limited to 10 entries.
2. THE response SHALL include `client_or_industry_tag`, `observed_pattern`, `frequency_count`, and `last_updated` for each insight.
3. IF no insights exist in the database, THEN THE Web_API SHALL return an empty list with HTTP 200.
4. THE Reflex_UI SHALL display a collapsible sidebar section containing advisory cards showing the tag, pattern, and frequency for each insight.
5. THE Reflex_UI SHALL render a badge on the sidebar section header indicating the number of available insights.
6. THE Reflex_UI SHALL refresh the insights data when the user navigates to a project or version detail view.

---

### Requirement 11 — Version-Level Proposal Listing (Gap 11)

**User Story:** As a reviewer, I want to see all proposals generated for a version on the version detail page so that I can track synthesis history alongside reviews.

#### Acceptance Criteria

1. WHEN a GET request is received at `/api/versions/{version_id}/proposals`, THE Web_API SHALL return a list of all Proposal_Jobs whose linked reviews belong to the specified version, including proposal_id, status, creation date, progress_message, and linked review count.
2. IF no proposals exist for the version, THEN THE Web_API SHALL return an empty list with HTTP 200.
3. THE Reflex_UI SHALL display a "Proposals" section on the Version_Detail_Page listing all proposals for the current version.
4. WHEN a proposal status is "complete", THE Reflex_UI SHALL display the proposal row with a "View" action linking to the proposal detail.
5. WHEN a proposal status is "running" or "queued", THE Reflex_UI SHALL display a progress indicator on that proposal row.
6. THE Reflex_UI SHALL poll `/api/versions/{version_id}/proposals` at a regular interval while any proposal is in a non-terminal state (queued or running).
