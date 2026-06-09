# Requirements Document

## Introduction

Project Contexta is a deterministic solution validation pipeline — an open-source, terminal-based AI governance and proposal coaching workbench. It provides structured, schema-enforced review of solution proposals across 12 independent dimensions, surfacing risks, contradictions, and mitigation options to non-technical users through a Textual TUI.

The MVP scope covers **Layer 1 (Exploration)** and **Layer 2 (Synthesis)** only. Layer 3 (Decision) and Layer 4 (Learning) are deferred to Phase 2.

The system runs as a single-container Docker deployment, operates fully offline-first, and uses only open-source components. LLM inference is abstracted via LiteLLM to support Ollama, OpenAI, Anthropic, and any other LiteLLM-compatible backend.

---

## Glossary

- **Contexta**: The Project Contexta application as a whole.
- **TUI**: Terminal User Interface rendered by the Textual library.
- **MCP Host Client**: The Model Context Protocol client responsible for ingesting source files via stdio and SSE transports.
- **MCP Artifact View**: The left TUI pane displaying ingested files and line references.
- **Active Pipeline**: The right TUI pane displaying the metadata cluster and 12-dimension risk reconciliation view.
- **Dimension Review**: An independent asynchronous LLM-powered review task for one of the 12 ReviewDimensions.
- **ReviewDimension**: One of the 12 defined review axes: Intent, Scope, Ownership, Delivery, Timeline, Architecture, NFR, Resource, Risk, Commercial, Language, Consistency.
- **ReviewNodePayload**: The validated Pydantic model representing the structured output of a single dimension review.
- **IssueFinding**: A Pydantic model capturing a single identified issue within a ReviewNodePayload, including confidence rating and source citations.
- **SourceCitation**: A Pydantic model capturing a reference to a specific source file and line range, classified by CitationType.
- **CitationType**: Enum value — `Direct Reference` or `Advised in Relation`.
- **ConfidenceLevel**: Enum value — `RED`, `AMBER`, or `GREEN`.
- **MitigationRouting**: Enum value — `Scope Modification`, `Risk Register`, `Assumptions Matrix`, `Both R&A`, or `Ignored`.
- **Node**: A versioned unit of pipeline state stored in SQLite, scoped to a project and linked to a parent node via `parent_id`.
- **Fork**: The act of creating a new Node branched from an existing Node under the same project, preserving lineage via `parent_id`.
- **Arbitrator Persona**: The LLM persona used during Layer 2 synthesis to detect contradictions across dimension outputs.
- **Proactive Advisor**: The Layer 2 engine that evaluates global tag combinations and emits blocking advisory modals for high-risk patterns.
- **Unalterable Scope Policy**: The enforcement rule that prevents direct scope modification, routing changes instead to Risk Register or Assumptions Matrix.
- **Dream Cycle**: The Admin Tab-triggered background worker that analyses the global SQLite database and updates `global_client_insights`.
- **Prompt Blueprint**: A versioned master prompt stored in `prompt_blueprints`, used to drive dimension review and synthesis LLM calls.
- **Global Client Insights**: Aggregated pattern data stored in `global_client_insights`, surfaced as advisory hints in the TUI sidebar.
- **JSON Packet**: A flat, structured JSON export of the full pipeline state for a given node.
- **Temperature-Zero Mode**: LLM inference configuration enforcing `temperature=0.0` and JSON-mode output to ensure deterministic responses.
- **CitationJumpRequested**: A custom Textual Message emitted by the PipelineView when an IssueFinding is selected, carrying the file_path, line_start, and line_end of the first SourceCitation in that finding.
- **Execution Mode**: A configuration toggle (`UNIFIED` or `PARALLEL`). `UNIFIED` evaluates all 12 dimensions in a single LLM call and parses the response into 12 independent `ReviewNodePayload` objects to save tokens; `PARALLEL` runs 12 independent async calls concurrently. Defaults to `UNIFIED`.

---

## Requirements

### Requirement 1 — Application Bootstrapping and Container Deployment

**User Story:** As an operator, I want to run Project Contexta from a single Docker container so that I can deploy it in isolated, reproducible environments without external dependencies.

#### Acceptance Criteria

1. THE Contexta SHALL be packaged as a single Docker container image that runs entirely offline once the image is built.
2. THE Contexta SHALL require Python 3.11 or later as its runtime baseline.
3. WHEN the container starts, THE Contexta SHALL launch the Textual TUI without requiring any manual pre-configuration beyond environment variable injection.
4. THE Contexta SHALL expose LLM backend selection via an environment variable accepting any LiteLLM-supported backend identifier (e.g., `ollama/mistral`, `openai/gpt-4o`, `anthropic/claude-3`), AND SHALL expose a `CONTEXTA_EXECUTION_MODE` environment variable defaulting to `UNIFIED`.
5. IF a required environment variable is missing at startup, THEN THE Contexta SHALL display a descriptive error message in the TUI and halt initialisation.

---

### Requirement 2 — SQLite Data Layer

**User Story:** As a developer, I want all persistent state stored in a local, file-backed SQLite database so that no external database infrastructure is required.

#### Acceptance Criteria

1. THE Contexta SHALL initialise a SQLite database with the following tables on first run: `projects`, `nodes`, `prompt_blueprints`, `global_client_insights`.
2. THE `projects` table SHALL store columns: `id` (primary key), `name` (text), `global_tags` (JSON text).
3. THE `nodes` table SHALL store columns: `id` (primary key), `project_id` (foreign key → projects.id), `parent_id` (nullable foreign key → nodes.id), `layer_type` (text), `node_name` (text), `version_tag` (text), `metadata_json` (JSON text), `content_markdown` (text), `created_at` (ISO-8601 timestamp).
4. THE `prompt_blueprints` table SHALL store columns: `id` (primary key), `blueprint_name` (text), `version_string` (text), `master_prompt_text` (text), `is_active` (boolean).
5. THE `global_client_insights` table SHALL store columns: `id` (primary key), `client_or_industry_tag` (text), `observed_pattern` (text), `frequency_count` (integer), `last_updated` (ISO-8601 timestamp), with a unique index on `(client_or_industry_tag, observed_pattern)`.
6. WHEN a Node is written to the `nodes` table, THE Contexta SHALL validate the node payload against the `ReviewNodePayload` Pydantic model before committing.
7. IF Pydantic validation fails for a node write, THEN THE Contexta SHALL reject the write, log the validation error to the TUI footer, and leave the existing database state unchanged.

---

### Requirement 3 — Pydantic Schema Enforcement

**User Story:** As a developer, I want all structured LLM outputs and stored records validated against strict Pydantic schemas so that malformed or incomplete data never enters the pipeline.

#### Acceptance Criteria

1. THE Contexta SHALL define a `ConfidenceEnum` Pydantic enum with values `RED`, `AMBER`, and `GREEN`.
2. THE Contexta SHALL define a `CitationTypeEnum` Pydantic enum with values `Direct Reference` and `Advised in Relation`.
3. THE Contexta SHALL define a `ReviewDimensionEnum` Pydantic enum with exactly 12 values: `Intent`, `Scope`, `Ownership`, `Delivery`, `Timeline`, `Architecture`, `NFR`, `Resource`, `Risk`, `Commercial`, `Language`, `Consistency`.
4. THE Contexta SHALL define a `MitigationRoutingEnum` Pydantic enum with values `Scope Modification`, `Risk Register`, `Assumptions Matrix`, `Both R&A`, and `Ignored`.
5. THE Contexta SHALL define a `SourceCitation` Pydantic model with fields: `file_path` (str), `line_start` (int), `line_end` (int), `citation_type` (CitationTypeEnum), `excerpt` (str).
6. THE Contexta SHALL define an `IssueFinding` Pydantic model with fields: `dimension` (ReviewDimensionEnum), `confidence` (ConfidenceEnum), `summary` (str), `detail` (str), `citations` (list of SourceCitation), `mitigation_routing` (MitigationRoutingEnum).
7. THE Contexta SHALL define a `ReviewNodePayload` Pydantic model with fields: `dimension` (ReviewDimensionEnum), `findings` (list of IssueFinding), `overall_confidence` (ConfidenceEnum), `raw_llm_response` (str).
8. WHEN an LLM response is received for a dimension review, THE Contexta SHALL parse and validate the response against `ReviewNodePayload` before any downstream processing occurs.
9. IF LLM response parsing produces a Pydantic validation error, THEN THE Contexta SHALL mark the corresponding dimension task as `FAILED` and display the validation error in the Active Pipeline pane.

---

### Requirement 4 — MCP Host Client and File Ingestion

**User Story:** As a user, I want to ingest project source files into the pipeline via the MCP protocol so that the AI review has grounded, citable source material.

#### Acceptance Criteria

1. THE MCP Host Client SHALL support file ingestion via both `stdio` and `SSE` MCP transports.
2. WHEN a source file is ingested via the MCP Host Client, THE MCP Artifact View SHALL display the file name and line count in the left TUI pane.
3. THE MCP Artifact View SHALL display each ingested file as a selectable entry with a line-reference indicator showing the total number of lines available for citation.
4. WHEN a user selects an ingested file in the MCP Artifact View, THE Contexta SHALL display a scrollable preview of the file content within the left TUI pane.
5. THE Contexta SHALL associate all SourceCitation objects produced during dimension reviews with a specific ingested file and line range, using the file's path as recorded during ingestion.
6. IF an MCP transport connection fails during ingestion, THEN THE MCP Host Client SHALL display an error notification in the TUI footer bar describing the failure and the transport type that failed.

---

### Requirement 5 — Layer 1: 12-Dimension Exploration

**User Story:** As a user, I want the system to independently review a solution proposal across 12 defined dimensions so that I receive comprehensive, grounded risk intelligence for each aspect of the proposal.

#### Acceptance Criteria

1. WHEN a Layer 1 review is initiated AND `CONTEXTA_EXECUTION_MODE` is `PARALLEL`, THE Contexta SHALL launch exactly 12 concurrent asynchronous dimension review tasks, one per ReviewDimension. IF `CONTEXTA_EXECUTION_MODE` is `UNIFIED`, THE Contexta SHALL launch a single LLM task that returns a consolidated JSON array of 12 dimension results, which is then parsed and validated into 12 independent `ReviewNodePayload` objects.
2. THE Contexta SHALL execute all LLM calls for dimension reviews with `temperature=0.0` and JSON-mode output enforced.
3. THE Contexta SHALL use the active Prompt Blueprint from `prompt_blueprints` (where `is_active = true`) to construct the LLM prompt for each dimension review.
4. WHEN all 12 dimension payloads are successfully validated — whether generated concurrently via `PARALLEL` mode or parsed from a single unified LLM response in `UNIFIED` mode — THE Contexta SHALL commit all 12 payloads in a single atomic write to the `nodes` table to prevent partial Layer 1 records.
5. THE Active Pipeline pane SHALL display a live status indicator for each of the 12 dimensions, reflecting one of the following states: `PENDING`, `RUNNING`, `COMPLETE`, `FAILED`.
6. WHEN a dimension review task is in `FAILED` state, THE Contexta SHALL allow the user to independently restart that specific dimension task without restarting the remaining 11 tasks.
7. WHILE a dimension review task is in `RUNNING` state, THE Active Pipeline pane SHALL display a progress indicator for that dimension.
8. THE Contexta SHALL extract `SourceCitation` dicts from each LLM JSON response and attach them to the corresponding `IssueFinding` objects within the `ReviewNodePayload`.

---

### Requirement 6 — Layer 2: Compare and Reconciliation (Arbitrator)

**User Story:** As a user, I want the system to detect contradictions across the 12 dimension outputs so that I can understand where the review findings conflict before acting on them.

#### Acceptance Criteria

1. WHEN the user triggers the Compare action (`[C]` footer key), THE Contexta SHALL invoke the Arbitrator Persona LLM call, passing all 12 completed `ReviewNodePayload` objects as input context.
2. THE Arbitrator Persona SHALL operate with `temperature=0.0` and JSON-mode output enforced.
3. WHEN the Arbitrator Persona completes, THE Active Pipeline pane SHALL display a reconciliation summary highlighting any contradictions detected between dimension findings.
4. THE Contexta SHALL store the Arbitrator reconciliation output as a new Node in the `nodes` table with `layer_type = 'synthesis'`, linked to the Layer 1 node via `parent_id`.
5. IF the Compare action is triggered before all 12 dimension reviews have reached `COMPLETE` state, THEN THE Contexta SHALL display a blocking warning modal listing the dimensions that have not yet completed, and SHALL NOT proceed with the Arbitrator call.

---

### Requirement 7 — Layer 2: Fork Iteration

**User Story:** As a user, I want to fork the current pipeline state into a versioned branch so that I can explore alternative review paths without overwriting the original findings.

#### Acceptance Criteria

1. WHEN the user triggers the Fork action (`[F]` footer key), THE Contexta SHALL create a new Node in the `nodes` table with `parent_id` set to the ID of the currently active Node.
2. THE new forked Node SHALL inherit the `project_id` and `global_tags` of the parent Node.
3. THE Contexta SHALL prompt the user to provide a name for the forked Node before committing the fork.
4. WHEN a fork is committed, THE Active Pipeline pane header SHALL update to display the name of the newly active forked Node.
5. THE Contexta SHALL allow the user to navigate between forked Nodes within the same project from the Active Pipeline pane.

---

### Requirement 8 — Layer 2: Proactive Advisor and High-Risk Blocking Modal

**User Story:** As a user, I want the system to proactively warn me when my project's tag combination matches a known high-risk pattern so that I can make an informed decision before proceeding.

#### Acceptance Criteria

1. WHEN Layer 2 synthesis begins, THE Proactive Advisor SHALL evaluate the active project's `global_tags` against known high-risk tag combination patterns stored in `global_client_insights`.
2. WHEN a high-risk tag combination is detected (e.g., `#Lean-Client-Team` combined with `#Complex-Testing`), THE Contexta SHALL display a blocking modal before allowing the user to proceed with synthesis.
3. THE blocking modal SHALL display the detected tag combination, the observed pattern from `global_client_insights`, and the frequency count of previous occurrences.
4. THE blocking modal SHALL require the user to explicitly acknowledge the risk before dismissing.
5. WHEN the user dismisses the blocking modal, THE Contexta SHALL record the acknowledgement in the active Node's `metadata_json`.

---

### Requirement 9 — Layer 2: Unalterable Scope Policy

**User Story:** As a user, I want the system to enforce that scope changes are never silently accepted so that all scope-related decisions are routed to appropriate governance artefacts.

#### Acceptance Criteria

1. WHEN an `IssueFinding` with `mitigation_routing = 'Scope Modification'` is detected in any dimension output, THE Contexta SHALL display a routing toggle in the Active Pipeline pane for that finding.
2. THE routing toggle SHALL offer exactly three options: `[Change Scope]`, `[Route to Risk Register]`, `[Route to Assumptions Matrix]`.
3. WHEN the user selects `[Route to Risk Register]`, THE Contexta SHALL update the finding's `mitigation_routing` to `Risk Register` and record the decision in the active Node's `metadata_json`.
4. WHEN the user selects `[Route to Assumptions Matrix]`, THE Contexta SHALL update the finding's `mitigation_routing` to `Assumptions Matrix` and record the decision in the active Node's `metadata_json`.
5. WHEN the user selects `[Change Scope]`, THE Contexta SHALL display a confirmation modal requiring explicit acknowledgement that a scope change has been approved before updating the finding's `mitigation_routing` to `Scope Modification` in `metadata_json`. THE Contexta SHALL then append a `#MUTATED` tag to the active Node's `global_tags` in the `metadata_json` and SHALL display a TUI notification advising the user to re-run the Exploration Layer, as the original artifact context is now out of sync with the modified scope.

---

### Requirement 10 — TUI Layout and Navigation

**User Story:** As a non-technical user, I want a clear, consistently structured terminal interface so that I can navigate the pipeline, view findings, and trigger actions without requiring command-line expertise.

#### Acceptance Criteria

1. THE TUI SHALL render a persistent header displaying: current project name, active Node name, and an Admin Tab access indicator.
2. THE TUI SHALL render a persistent left pane containing the MCP Artifact View (ingested file browser with line references).
3. THE TUI SHALL render a persistent right pane containing the Active Pipeline (metadata cluster and 12-dimension risk reconciliation view).
4. THE TUI SHALL render a persistent footer action bar with the following labelled keys: `[F] Fork Iteration`, `[C] Compare`, `[P] Run Proposal Generator`, `[E] Export Flat JSON Packet`.
5. WHEN a footer action key is pressed, THE TUI SHALL respond within 200ms with either an immediate action or a modal requiring user input.
6. THE TUI SHALL be keyboard-navigable without requiring a mouse.
7. WHERE a project contains multiple Nodes, THE TUI SHALL allow the user to switch between Nodes using keyboard navigation within the Active Pipeline pane.
8. WHEN an IssueFinding is highlighted or selected in the Active Pipeline pane, THE TUI SHALL emit a `CitationJumpRequested` message carrying the `file_path`, `line_start`, and `line_end` from the finding's first SourceCitation.
9. WHEN a `CitationJumpRequested` message is received by the ArtifactView, THE ArtifactView SHALL scroll the file content preview to bring `line_start` into view and SHALL visually highlight all lines in the range `[line_start, line_end]` using a distinct highlight style until a different finding is selected or the user navigates away.

---

### Requirement 11 — Export: Flat JSON Packet

**User Story:** As a user, I want to export the full pipeline state for the active Node as a flat JSON file so that I can share or archive the review output in a portable, system-agnostic format.

#### Acceptance Criteria

1. WHEN the user triggers the Export action (`[E]` footer key), THE Contexta SHALL serialise the active Node's complete pipeline state — including all `ReviewNodePayload` objects, Arbitrator output (if present), routing decisions, and `metadata_json` — into a single flat JSON file.
2. THE exported JSON file SHALL include a `schema_version` field identifying the Contexta data schema version used.
3. THE exported JSON file SHALL be written to a user-configurable output path, defaulting to the current working directory.
4. WHEN the export completes, THE TUI footer bar SHALL display a confirmation message including the full output file path.
5. IF the export fails due to a filesystem error, THEN THE Contexta SHALL display the error description in the TUI footer bar and SHALL NOT produce a partial file.

---

### Requirement 12 — Structured JSON Import

**User Story:** As a user, I want to import a previously exported JSON Packet so that I can resume or review a prior pipeline session without re-running LLM inference.

#### Acceptance Criteria

1. THE Contexta SHALL provide a JSON import command accessible from the Admin Tab.
2. WHEN a JSON Packet is imported, THE Contexta SHALL validate the file against the current `ReviewNodePayload` and Node schemas before writing any data to the SQLite database.
3. IF the imported JSON Packet fails schema validation, THEN THE Contexta SHALL display the validation errors in the TUI and SHALL NOT write any data to the database.
4. WHEN a valid JSON Packet is imported successfully, THE Contexta SHALL create a new Node in the `nodes` table representing the imported state, and SHALL navigate the Active Pipeline pane to that Node.

---

### Requirement 13 — Admin Tab: Dream Cycle

**User Story:** As an administrator, I want to manually trigger a background analysis of the global database so that the system can surface advisory hints based on recurring failure patterns across all projects.

#### Acceptance Criteria

1. THE Admin Tab SHALL be accessible from the TUI header and SHALL present a Dream Cycle trigger control.
2. WHEN the user triggers the Dream Cycle, THE Contexta SHALL launch a background worker that analyses the `nodes` table across all projects to identify recurring failure patterns.
3. WHILE the Dream Cycle worker is running, THE Admin Tab SHALL display a status indicator showing that the worker is active.
4. WHEN the Dream Cycle worker completes, THE Contexta SHALL update the `global_client_insights` table with newly identified or updated patterns, incrementing `frequency_count` for existing `(client_or_industry_tag, observed_pattern)` pairs, and inserting new rows for novel patterns.
5. WHEN `global_client_insights` is updated by the Dream Cycle, THE TUI sidebar SHALL surface the top advisory hints derived from the updated data.
6. IF the Dream Cycle worker encounters an unhandled error, THEN THE Contexta SHALL log the error in the Admin Tab panel and SHALL terminate the worker without corrupting the `global_client_insights` table.

---

### Requirement 14 — Prompt Blueprint Management

**User Story:** As an administrator, I want to manage versioned prompt blueprints so that I can update LLM prompts without modifying application code.

#### Acceptance Criteria

1. THE Admin Tab SHALL provide a Prompt Blueprint management interface listing all records in `prompt_blueprints`.
2. WHEN an administrator activates a Prompt Blueprint, THE Contexta SHALL set `is_active = true` for that blueprint and `is_active = false` for all other blueprints in `prompt_blueprints`.
3. THE Contexta SHALL ensure exactly one Prompt Blueprint has `is_active = true` at any given time.
4. WHEN a new Prompt Blueprint version is saved, THE Contexta SHALL assign a new `version_string` and store the record as a new row without modifying or deleting the prior version.
5. IF no Prompt Blueprint has `is_active = true` when a dimension review is triggered, THEN THE Contexta SHALL display a blocking error in the TUI and SHALL NOT proceed with the LLM call.
