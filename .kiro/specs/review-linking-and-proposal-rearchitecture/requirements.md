# Requirements Document

## Introduction

This feature set introduces two architectural enhancements to Project Contexta's web-based review and proposal pipeline:

1. **Review Linking** — enables users to associate one or more historical reviews as context when creating a new review session. Linked review findings are injected as structured prior intelligence into the LLM prompt, grounding new reviews in previously identified risks and patterns. Linking is one-directional: only the new review stores references to its linked predecessors.

2. **Proposal Creation Re-Architecture** — elevates proposal generation from a single-review child operation to a version-level artifact that can draw on multiple reviews. A new junction table replaces the existing `proposal_jobs.review_job_id` FK, enabling multi-review synthesis. Existing data is migrated transparently. Multiple independent proposals per version are stored alongside each other for comparison.

Both features share the existing technical foundation: aiosqlite async persistence, LiteLLM temperature=0.0 JSON-mode inference, Reflex frontend, and FastAPI backend. All schema changes use idempotent DDL migrations (`CREATE TABLE IF NOT EXISTS`) and maintain backward compatibility with existing data.

---

## Glossary

- **Contexta**: The Project Contexta application (FastAPI backend + Reflex frontend).
- **Review_Job**: A row in `review_jobs` representing an asynchronous 12-dimension pipeline execution scoped to a version.
- **Proposal_Job**: A row in `proposal_jobs` representing an asynchronous Layer 2 synthesis execution.
- **Review_Link**: A junction table row associating a new review with a historical review it uses as context.
- **Proposal_Review_Link**: A junction table row associating a proposal with one or more source reviews whose findings contribute to synthesis.
- **Prior_Review_Intelligence**: A structured JSON section injected into the LLM prompt containing per-dimension findings extracted from linked historical reviews.
- **Version**: A named iteration within a project, grouping artifacts and reviews. Stored in the `versions` table.
- **Junction_Table**: A many-to-many relational mapping table with composite primary keys.
- **Idempotent_Migration**: A DDL statement using `CREATE TABLE IF NOT EXISTS` that produces the same schema state regardless of how many times it executes.
- **Dimension_Payload**: A validated `ReviewNodePayload` object containing findings for one of the 12 review dimensions.
- **Structured_Injection**: The technique of formatting linked review findings as typed JSON objects within a dedicated prompt section, organized per-dimension.

---

## Requirements

### Requirement 1 — Review Links Junction Table

**User Story:** As a developer, I want a junction table that records which historical reviews were linked to a new review, so that the system can retrieve prior review context during pipeline execution.

#### Acceptance Criteria

1. THE Contexta SHALL create a `review_links` table with columns: `review_id` (TEXT NOT NULL, FK → review_jobs.id), `linked_review_id` (TEXT NOT NULL, FK → review_jobs.id), and a composite PRIMARY KEY on (`review_id`, `linked_review_id`).
2. THE Contexta SHALL create the `review_links` table using a `CREATE TABLE IF NOT EXISTS` DDL statement within the idempotent migration runner.
3. WHEN a row is inserted into `review_links`, THE Contexta SHALL enforce that `review_id` differs from `linked_review_id` via a CHECK constraint.
4. THE Contexta SHALL enforce foreign key integrity on both `review_id` and `linked_review_id` columns referencing `review_jobs.id`.

---

### Requirement 2 — Proposal Review Links Junction Table

**User Story:** As a developer, I want a junction table that maps proposals to their source reviews, so that proposal generation can draw findings from multiple reviews.

#### Acceptance Criteria

1. THE Contexta SHALL create a `proposal_review_links` table with columns: `proposal_id` (TEXT NOT NULL, FK → proposal_jobs.id), `review_id` (TEXT NOT NULL, FK → review_jobs.id), and a composite PRIMARY KEY on (`proposal_id`, `review_id`).
2. THE Contexta SHALL create the `proposal_review_links` table using a `CREATE TABLE IF NOT EXISTS` DDL statement within the idempotent migration runner.
3. THE Contexta SHALL enforce foreign key integrity on both `proposal_id` and `review_id` columns referencing their respective parent tables.

---

### Requirement 3 — Legacy Proposal Data Migration

**User Story:** As a user with existing proposals, I want my previous proposal-to-review relationships preserved in the new junction table, so that historical data remains accessible under the new architecture.

#### Acceptance Criteria

1. WHEN the migration runner detects existing rows in `proposal_jobs` with a non-null `review_job_id` column, THE Contexta SHALL insert a corresponding row into `proposal_review_links` for each such proposal (mapping `proposal_jobs.id` → `proposal_id`, `proposal_jobs.review_job_id` → `review_id`).
2. THE Contexta SHALL execute the data migration within the same migration transaction as the DDL changes, ensuring atomicity.
3. IF a `proposal_review_links` row already exists for a given (`proposal_id`, `review_id`) pair, THEN THE Contexta SHALL skip that row without error (idempotent re-run safety).
4. THE Contexta SHALL retain the `review_job_id` column on `proposal_jobs` to maintain backward compatibility with the legacy `POST /api/proposals` endpoint.

---

### Requirement 4 — Create Review with Linked Reviews

**User Story:** As a user, I want to select historical reviews as context when creating a new review, so that the LLM pipeline can reference prior findings during analysis.

#### Acceptance Criteria

1. THE `CreateReviewRequest` schema SHALL accept an optional field `linked_review_ids` of type `list[str]` defaulting to an empty list.
2. WHEN `linked_review_ids` is non-empty in a create review request, THE Contexta SHALL validate that each ID references an existing `review_jobs` row with `status = 'complete'`.
3. IF any ID in `linked_review_ids` references a non-existent or non-complete review, THEN THE Contexta SHALL return HTTP 422 with a descriptive error message identifying the invalid ID.
4. WHEN a review job is created with valid `linked_review_ids`, THE Contexta SHALL insert one row into `review_links` per linked review ID before returning the 202 response.
5. THE Contexta SHALL store review links within the same database transaction as the review job creation.

---

### Requirement 5 — List Available Reviews for Linking

**User Story:** As a user, I want to see which historical reviews are available to link when creating a new review, so that I can make informed selections.

#### Acceptance Criteria

1. THE Contexta SHALL expose a `GET /api/versions/{version_id}/reviews/linkable` endpoint returning all review jobs for that version with `status = 'complete'`.
2. THE response SHALL include for each review: `review_id`, `persona`, `run_date`, and `finding_count` (total number of findings across all dimensions).
3. WHEN no completed reviews exist for the version, THE endpoint SHALL return an empty list with HTTP 200.

---

### Requirement 6 — Prior Review Intelligence Injection

**User Story:** As a user, I want linked review findings injected into the LLM prompt as structured context, so that the new review benefits from prior analysis.

#### Acceptance Criteria

1. WHEN the review pipeline executes for a review job with linked reviews, THE Contexta SHALL extract all `ReviewNodePayload` objects from each linked review's exploration node.
2. THE Contexta SHALL format extracted findings as a structured JSON array organized per-dimension, with each entry containing: `dimension`, `confidence`, `summary`, and `source_review_id`.
3. THE Contexta SHALL inject the formatted findings into a dedicated "Prior Review Intelligence" section of the LLM system prompt, positioned after the master blueprint text and before the artifact context.
4. WHILE building the Prior Review Intelligence section, THE Contexta SHALL limit the injected content to findings with confidence level `RED` or `AMBER` to control prompt token usage.
5. IF a linked review's exploration node cannot be loaded (deleted or corrupted), THEN THE Contexta SHALL log a warning and continue pipeline execution without that review's findings.

---

### Requirement 7 — Version-Level Proposal Creation Endpoint

**User Story:** As a user, I want to generate a proposal from multiple reviews at the version level, so that synthesis can consolidate findings across different review sessions.

#### Acceptance Criteria

1. THE Contexta SHALL expose a `POST /api/versions/{version_id}/proposals` endpoint accepting a request body with `review_ids: list[str]` (minimum one entry).
2. WHEN the endpoint receives a valid request, THE Contexta SHALL validate that all `review_ids` reference completed review jobs belonging to the specified `version_id`.
3. IF any review ID is invalid, non-complete, or belongs to a different version, THEN THE Contexta SHALL return HTTP 422 with a descriptive error message.
4. WHEN validation passes, THE Contexta SHALL create a `proposal_jobs` row and insert one `proposal_review_links` row per review ID.
5. THE Contexta SHALL launch the proposal synthesis pipeline as a background task, returning HTTP 202 with the `proposal_id` and `status = 'queued'`.
6. THE proposal pipeline SHALL load dimension payloads from all linked reviews' exploration nodes and consolidate their findings before invoking the Layer 2 arbitrator.

---

### Requirement 8 — Legacy Proposal Endpoint Backward Compatibility

**User Story:** As an existing API consumer, I want the current `POST /api/proposals` endpoint to continue working, so that no integration breaks during the transition.

#### Acceptance Criteria

1. THE existing `POST /api/proposals` endpoint SHALL continue to accept `CreateProposalRequest` with a single `review_id` field.
2. WHEN the legacy endpoint receives a request, THE Contexta SHALL create the proposal job and insert a single row into `proposal_review_links` mapping the proposal to the specified review.
3. THE legacy endpoint SHALL set `proposal_jobs.review_job_id` to the provided review ID for backward compatibility with existing status-polling logic.
4. THE legacy endpoint response format SHALL remain unchanged (HTTP 202 with `proposal_id` and `status`).

---

### Requirement 9 — Multiple Independent Proposals per Version

**User Story:** As a user, I want to generate multiple proposals for the same version, so that I can compare different synthesis outputs side by side.

#### Acceptance Criteria

1. THE Contexta SHALL allow multiple `proposal_jobs` rows to reference the same version (via their linked reviews), with no uniqueness constraint preventing repeated proposal generation.
2. THE Contexta SHALL expose a `GET /api/versions/{version_id}/proposals` endpoint returning all proposals associated with that version, ordered by `created_at` descending.
3. THE response SHALL include for each proposal: `proposal_id`, `status`, `created_at`, `review_count` (number of linked reviews), and `progress_message`.

---

### Requirement 10 — Review Linking UI Component

**User Story:** As a user, I want a visual multi-select interface on the Run Review page showing completed historical reviews, so that I can choose which prior reviews to link.

#### Acceptance Criteria

1. WHEN the Run Review page (`/run-review/{version_id}`) loads, THE Contexta frontend SHALL fetch available linkable reviews from `GET /api/versions/{version_id}/reviews/linkable`.
2. THE frontend SHALL render completed reviews as selectable chip elements displaying the persona name and run date.
3. WHEN no completed reviews exist for the version, THE frontend SHALL hide the review linking section entirely.
4. WHEN the user submits the review form with selected linked reviews, THE frontend SHALL include the selected review IDs in the `linked_review_ids` field of the `CreateReviewRequest`.
5. THE chip selection state SHALL be independent of the persona role selection — linking reviews does not affect which persona roles are chosen for the new review.

---

### Requirement 11 — Proposal Generation UI on Version Detail

**User Story:** As a user, I want a "Generate Proposal" section on the version detail view with a review checklist, so that I can select which reviews to synthesize into a proposal.

#### Acceptance Criteria

1. THE version detail component SHALL render a "Generate Proposal" section below the existing review runs list.
2. THE "Generate Proposal" section SHALL display a checklist of all completed reviews for the selected version, showing persona and run date per entry.
3. WHEN the user selects one or more reviews and clicks "Generate Proposal", THE frontend SHALL POST to `POST /api/versions/{version_id}/proposals` with the selected `review_ids`.
4. WHILE a proposal is being generated, THE frontend SHALL display a progress indicator with status polling against the proposal status endpoint.
5. WHEN no completed reviews exist, THE "Generate Proposal" section SHALL display a disabled state with explanatory text.
6. THE frontend SHALL display a list of existing proposals for the version (fetched from `GET /api/versions/{version_id}/proposals`) with their status and creation date.

---

### Requirement 12 — Schema Version Increment

**User Story:** As a developer, I want the database schema version incremented to reflect the new tables, so that the migration runner applies changes correctly on existing installations.

#### Acceptance Criteria

1. THE Contexta SHALL increment `SCHEMA_VERSION` from its current value to the next integer when the `review_links` and `proposal_review_links` tables are added.
2. THE migration runner SHALL apply the new DDL statements idempotently on both fresh installations and existing databases at prior schema versions.
3. THE migration runner SHALL execute the legacy data migration (Requirement 3) only when upgrading from a schema version that predates the `proposal_review_links` table.

