# Implementation Plan: Project Contexta

## Overview

This plan implements the full MVP of Project Contexta — a deterministic solution validation pipeline with a Textual TUI, 12-dimension asynchronous LLM review, SQLite persistence, MCP file ingestion, Layer 2 synthesis, and Admin tooling. Tasks are ordered from foundational infrastructure (config, DB, Pydantic models) through pipeline logic, TUI rendering, and finally integration wiring.

All tasks are in Python 3.11+. The design document at `.kiro/specs/project-contexta/design.md` is the authoritative reference for all interfaces, class signatures, and module boundaries.

---

## Tasks

- [ ] 1. Project scaffold and environment configuration
  - [ ] 1.1 Create the `contexta/` package directory structure with all `__init__.py` files
    - Create all subdirectories: `db/`, `models/`, `llm/`, `mcp/`, `pipeline/`, `admin/`, `tui/`, `tui/screens/`, `tui/widgets/`, `export/`
    - Add a `__init__.py` to each package directory
    - Create `pyproject.toml` declaring `python = "^3.11"` and all dependencies: `textual`, `pydantic`, `pydantic-settings`, `aiosqlite`, `litellm`, `mcp`
    - Create `Dockerfile` as defined in design §3
    - _Requirements: 1.1, 1.2_

  - [ ] 1.2 Implement `contexta/config.py` — environment parsing and `ContextaConfig`
    - Implement `ContextaConfig(BaseSettings)` with all fields including `execution_mode: str = "UNIFIED"` and the `validate_backend` validator exactly as defined in design §3
    - Add `validate_execution_mode` validator: accepts only `"UNIFIED"` or `"PARALLEL"`, raises `ConfigError` for any other value
    - Implement `load_config()` raising `ConfigError` on failure
    - Define `ConfigError` exception class
    - _Requirements: 1.3, 1.4, 1.5_

  - [ ]* 1.3 Write property tests for `ContextaConfig`
    - **Property 1: LiteLLM Backend String Acceptance** — generate arbitrary `"provider/model"` strings and assert acceptance; generate arbitrary strings without `/` and assert `ConfigError`
    - **Property 2: Missing Environment Variable Rejection** — for any non-empty subset of required env vars absent from the environment, assert `load_config()` raises `ConfigError`
    - **Validates: Requirements 1.4, 1.5**

  - [ ]* 1.4 Write property test for execution mode validation
    - **Property 24: Execution Mode Validation** — assert `"UNIFIED"` and `"PARALLEL"` are accepted; assert any other string raises `ConfigError` with a descriptive message
    - **Validates: Requirements 1.4, 5.1**

- [ ] 2. Pydantic schema layer — enums, models, and validation pipeline
  - [ ] 2.1 Implement `contexta/models/enums.py` — all four enums
    - `ConfidenceEnum` (RED, AMBER, GREEN)
    - `CitationTypeEnum` (Direct Reference, Advised in Relation)
    - `ReviewDimensionEnum` (exactly 12 values)
    - `MitigationRoutingEnum` (5 values)
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 2.2 Write property test for enum round-trip serialisation
    - **Property 3: Pydantic Enum Round-Trip Serialization** — for every value in every enum, serialise to string and reconstruct; assert equality
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

  - [ ] 2.3 Implement `contexta/models/citations.py` — `SourceCitation` model
    - Include `@validator("line_end")` enforcing `line_end >= line_start`
    - _Requirements: 3.5_

  - [ ] 2.4 Implement `contexta/models/findings.py` — `IssueFinding` model
    - _Requirements: 3.6_

  - [ ] 2.5 Implement `contexta/models/payloads.py` — `ReviewNodePayload` model
    - _Requirements: 3.7_

  - [ ]* 2.6 Write property test for `ReviewNodePayload` round-trip serialisation
    - **Property 4: ReviewNodePayload Round-Trip Serialization** — generate arbitrary valid `ReviewNodePayload` objects using Hypothesis strategies; assert `model_dump_json()` → `model_validate_json()` round-trip equality
    - **Validates: Requirements 3.5, 3.6, 3.7, 3.8**

  - [ ]* 2.7 Write property test for LLM response validation gate
    - **Property 5: LLM Response Validation Gate** — generate valid `ReviewNodePayload` JSON and assert parse succeeds; generate schema-violating JSON (wrong types, missing fields, invalid enum values) and assert `ValidationError` is raised with no side-effects
    - **Validates: Requirements 3.8, 3.9, 2.6, 2.7**

  - [ ] 2.8 Implement `contexta/models/export.py` — `JSONPacket` and `ExportArbitratorResult` models
    - Include `EXPORT_SCHEMA_VERSION = "1.0"` constant and default on `schema_version` field
    - _Requirements: 11.1, 11.2_

- [ ] 3. SQLite data access layer
  - [ ] 3.1 Implement `contexta/db/schema.py` — DDL, `SCHEMA_VERSION`, and migration runner
    - Define all five `CREATE TABLE IF NOT EXISTS` DDL statements (including `schema_version`) as per design §5.1
    - The `nodes` table DDL MUST include `version_tag TEXT NOT NULL` column after `node_name`
    - Implement `run_migrations(conn)` that checks `schema_version`, runs outstanding DDL, and writes the current version
    - Implement `init_database(db_path)` that opens an `aiosqlite.Connection`, enables `PRAGMA foreign_keys = ON`, and calls `run_migrations`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ] 3.2 Implement `contexta/db/models.py` — Python dataclasses mirroring DB row shapes
    - Define `ProjectRow`, `NodeRow` (including `version_tag: str` field), `BlueprintRow`, `InsightRow` dataclasses
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [ ] 3.3 Implement `contexta/db/repositories.py` — all async repository functions
    - `create_project`, `get_project`
    - `write_node` (with Pydantic re-validation guard as per design §5.2), `get_node`, `list_nodes_for_project`, `fork_node`, `list_all_nodes`
    - `get_active_blueprint`, `activate_blueprint` (atomic transaction — sets one active, clears all others), `save_blueprint_version`, `list_blueprints`
    - `upsert_insight` (INSERT … ON CONFLICT … DO UPDATE), `get_insights_for_tags`
    - `write_node()` signature now includes `version_tag: str` parameter after `node_name`; INSERT uses 9 placeholders as per design §5.2
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 7.1, 7.2, 13.4, 14.2, 14.3_

  - [ ]* 3.4 Write property test for DB node write validation guard
    - **Property 6: DB Node Write Validation Guard** — call `write_node()` with an invalid payload (mutated after construction); assert no row is inserted and `ValidationError` is raised
    - **Validates: Requirements 2.6, 2.7**

  - [ ]* 3.5 Write property test for one-active blueprint invariant
    - **Property 21: One-Active Blueprint Invariant** — for any set of blueprint rows (including corrupted states with multiple active), call `activate_blueprint(id)` and assert exactly one row has `is_active = 1` and its id matches the argument
    - **Validates: Requirements 14.2, 14.3**

- [ ] 4. Checkpoint — foundation layer
  - Ensure all tests pass for config, models, and DB layers before proceeding. Ask the user if questions arise.

- [ ] 5. LiteLLM provider abstraction and prompt builder
  - [ ] 5.1 Implement `contexta/llm/provider.py` — `LLMConfig`, `LLMResponse`, `call_llm()`, `validate_backend()`
    - `call_llm()` must pass `temperature=0.0` and `response_format={"type": "json_object"}` to `litellm.acompletion()` on every call — no exceptions
    - Define `LLMCallError` exception class
    - _Requirements: 5.2, 6.2_

  - [ ]* 5.2 Write property test for Temperature-Zero LLM call invariant
    - **Property 10: Temperature-Zero LLM Call Invariant** — mock `litellm.acompletion`; for any valid `LLMConfig`, assert every call captures `temperature=0.0` and `response_format={"type": "json_object"}`
    - **Validates: Requirements 5.2, 6.2**

  - [ ] 5.3 Implement `contexta/llm/prompts.py` — `PromptBuilder` class
    - `DIMENSION_SYSTEM_TEMPLATE` must include CRITICAL OUTPUT INSTRUCTIONS block commanding raw, unwrapped JSON output — no markdown fences, no preamble, no commentary (as per design §6.2)
    - `build_dimension_prompt(dimension, artifact_context)` must embed `master_prompt_text` as a substring of the returned system prompt
    - `build_arbitrator_prompt(payloads)` must include the same CRITICAL OUTPUT INSTRUCTIONS block in its system string
    - `build_unified_prompt(artifact_context)` must request a JSON array of exactly 12 objects with CRITICAL OUTPUT INSTRUCTIONS commanding a raw JSON array (no fences), one object per ReviewDimension in order
    - Both PARALLEL and UNIFIED prompt builders enforce the explicit natural-language JSON directive as a defence-in-depth safeguard for local Ollama deployments
    - _Requirements: 5.2, 5.3_

  - [ ]* 5.4 Write property test for active blueprint prompt inclusion
    - **Property 11: Active Blueprint Prompt Inclusion** — for any `master_prompt_text` value `T` and any `ReviewDimensionEnum` value `D`, assert `build_dimension_prompt(D, ...)` system string contains `T`
    - **Validates: Requirements 5.3**

- [ ] 6. MCP Host Client and Artifact Registry
  - [ ] 6.1 Implement `contexta/mcp/artifact_registry.py` — `ArtifactRegistry` and `IngestedArtifact`
    - `register()`, `get()`, `all()`, `build_context_string()` as per design §7.2
    - _Requirements: 4.2, 4.3, 4.4_

  - [ ] 6.2 Implement `contexta/mcp/client.py` — `MCPHostClient`
    - `connect_stdio()` and `connect_sse()` async context managers
    - `ingest_file(uri)` reads resource, counts lines via `str.splitlines()`, registers in `ArtifactRegistry`, returns `IngestedArtifact`
    - `list_resources()`
    - Define `MCPIngestError` exception class
    - On transport connection failure, raise `MCPIngestError` with transport type in message
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

  - [ ]* 6.3 Write property test for artifact line count accuracy
    - **Property 7: Artifact Line Count Accuracy** — generate arbitrary multi-line strings; assert `IngestedArtifact.line_count == len(content.splitlines())`
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 6.4 Write property test for citation file path referential integrity
    - **Property 8: Citation File Path Referential Integrity** — register an artifact with path `P`; generate `SourceCitation` objects referencing that file; assert all `citation.file_path == P`
    - **Validates: Requirements 4.5, 5.8**

- [ ] 7. Pipeline — async dimension task orchestration (Layer 1)
  - [ ] 7.1 Implement `contexta/pipeline/dimension_runner.py` — `TaskState`, `DimensionTask`, `TaskOrchestrator`
    - `TaskOrchestrator.__init__` pre-populates exactly one `DimensionTask` per `ReviewDimensionEnum` value
    - `launch_all()` uses `asyncio.gather` to run all 12 dimensions concurrently
    - `retry_dimension()` resets a `FAILED` task to `PENDING` and re-runs it independently
    - `all_complete()`, `incomplete_dimensions()`, `get_all_payloads()`
    - State machine: PENDING → RUNNING → COMPLETE | FAILED
    - _Requirements: 5.1, 5.5, 5.6, 5.7_

  - [ ]* 7.2 Write property test for exactly 12 dimension tasks launched
    - **Property 9: Exactly 12 Dimension Tasks Launched** — mock the `runner_fn`; call `launch_all()`; assert exactly 12 tasks were invoked, one per `ReviewDimensionEnum` value, with no duplicates and no omissions
    - **Validates: Requirements 5.1**

  - [ ] 7.3 Implement `contexta/pipeline/dimension_runner.py` — `make_dimension_runner()` factory function
    - The runner function performs LLM call + Pydantic validation ONLY — it does NOT write to the database
    - Returns validated `ReviewNodePayload` to `DimensionTask.payload` (in-memory accumulator)
    - Raises `DimensionValidationError` on `ValidationError`; `TaskOrchestrator` catches it and marks task `FAILED`
    - Define `DimensionValidationError` exception class
    - _Requirements: 3.8, 3.9, 5.2, 5.3, 5.4, 5.8_

  - [ ] 7.4 Implement `commit_exploration_node()` — batch DB commit on Layer 1 completion
    - Called by the pipeline coordinator after `TaskOrchestrator.all_complete()` returns `True`
    - Calls `orchestrator.get_all_payloads()` to collect all 12 validated `ReviewNodePayload` objects from in-memory state
    - Builds `combined_metadata = {"dimensions": [p.model_dump() for p in payloads], "completed_at": ...}`
    - Executes a single `write_node()` call — the nodes table never contains a partial Layer 1 record
    - Raises `RuntimeError` if any dimension is not `COMPLETE`; raises `ValidationError` if DB-level re-validation fails
    - _Requirements: 5.4, 2.6, 2.7_

  - [ ] 7.6 Implement `contexta/pipeline/dimension_runner.py` — `make_unified_runner()` factory function
    - Called by the pipeline coordinator when `config.execution_mode == "UNIFIED"`
    - Makes a single LLM call via `call_llm()` requesting all 12 dimensions in one consolidated JSON array
    - Parses the outer array; raises `UnifiedRunnerError` if response is not a list of exactly 12 items
    - Validates each element against `ReviewNodePayload.model_validate()`; raises `UnifiedRunnerError` on any `ValidationError`
    - Returns a `list[ReviewNodePayload]` of exactly 12 items for `commit_exploration_node()`
    - Define `UnifiedRunnerError` exception class
    - Pipeline coordinator: if `UNIFIED`, call `run_unified()` then `commit_exploration_node()`; if `PARALLEL`, use `TaskOrchestrator.launch_all()` then `commit_exploration_node()`
    - _Requirements: 5.1, 5.4_

  - [ ]* 7.5 Write property test for Layer 1 batch commit atomicity
    - **Property 23: Layer 1 Batch Commit Atomicity** — generate a Layer 1 run with all 12 tasks COMPLETE; assert exactly one row is written to `nodes`; generate a run with at least one FAILED task; assert zero rows are written to `nodes`
    - **Validates: Requirements 5.4**

- [ ] 8. Pipeline — Layer 2 synthesis
  - [ ] 8.1 Implement `contexta/pipeline/arbitrator.py` — `ArbitratorEngine` and `ArbitratorResult`
    - `run(payloads)` raises `ArbitratorError` immediately if `len(payloads) != 12` (before any LLM call)
    - Uses `PromptBuilder.build_arbitrator_prompt()` and `call_llm()` (temperature=0.0 enforced by `call_llm`)
    - Parses JSON response; raises `ArbitratorError` on `JSONDecodeError`
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 8.2 Write property test for arbitrator 12-payload guard
    - **Property 13: Arbitrator Receives All 12 Payloads** — call `ArbitratorEngine.run()` with 0–11 payloads and assert `ArbitratorError` is raised before any LLM call is made
    - **Validates: Requirements 6.1**

  - [ ] 8.3 Implement `contexta/pipeline/advisor.py` — `ProactiveAdvisor` and `AdvisoryAlert`
    - `evaluate(global_tags, conn)` queries `get_insights_for_tags` and returns `AdvisoryAlert` for each matching `(client_tag, pattern)` pair
    - _Requirements: 8.1, 8.2_

  - [ ]* 8.4 Write property test for proactive advisor tag matching
    - **Property 16: Proactive Advisor Tag Matching** — generate arbitrary sets of `global_tags` and `InsightRow` collections; assert `evaluate()` returns alerts for all matching tags and no alerts for non-matching tags
    - **Validates: Requirements 8.1, 8.2**

  - [ ] 8.5 Implement `contexta/pipeline/scope_policy.py` — `ScopePolicyEnforcer`
    - `get_scope_findings(payloads)` filters all findings where `mitigation_routing == SCOPE_MODIFICATION`
    - `apply_routing_decision(finding, decision, metadata)` records entry in `metadata["routing_decisions"]` and returns updated metadata dict
    - `apply_mutated_tag(metadata)` appends `#MUTATED` to `metadata["tags"]` and sets `metadata["mutated_at"]` timestamp; called after `apply_routing_decision()` when decision is `SCOPE_MODIFICATION`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 8.6 Write property test for scope policy routing decision persistence
    - **Property 17: Scope Policy Routing Decision Persistence** — for any `IssueFinding` with `SCOPE_MODIFICATION` routing and any valid `MitigationRoutingEnum` decision, assert the returned metadata contains a `routing_decisions` entry whose `new_routing` equals `decision.value`
    - **Validates: Requirements 9.3, 9.4, 9.5**

- [ ] 9. Checkpoint — pipeline layer
  - Ensure all tests pass for LLM, MCP, and pipeline layers. Verify the full dimension run / arbitrator sequence works end-to-end in a unit test with mocked LLM calls. Ask the user if questions arise.

- [ ] 10. Admin layer — Dream Cycle and Blueprint Manager
  - [ ] 10.1 Implement `contexta/admin/dream_cycle.py` — `DreamCycleWorker`
    - `run(conn)` executes a single SQL query using `json_each(n.metadata_json, '$.dimensions')` as a table-valued function to extract RED-confidence dimension entries directly within SQLite — no full Python-level blob deserialization
    - SQL query: `SELECT p.global_tags, json_extract(dim.value, '$.dimension') FROM nodes n JOIN projects p ON p.id = n.project_id JOIN json_each(n.metadata_json, '$.dimensions') AS dim WHERE n.layer_type = 'exploration' AND json_extract(dim.value, '$.overall_confidence') = 'RED'`
    - Python loop iterates only the filtered `(global_tags, dimension_name)` result rows — not raw node blobs
    - Calls `upsert_insight(conn, tag, f"HIGH_RISK_{dimension_name.upper()}")` per `(tag, dimension)` pair
    - Continues processing on per-row errors (no abort); logs errors but does not re-raise
    - Returns count of rows created or updated
    - _Requirements: 13.2, 13.4, 13.6_

  - [ ]* 10.2 Write property test for Dream Cycle frequency count monotonicity
    - **Property 20: Dream Cycle Frequency Count Monotonicity** — generate a collection of `NodeRow` objects with `k ≥ 1` RED findings for a given `(client_tag, dimension)` pair; run `DreamCycleWorker`; assert `frequency_count ≥ k`; run again and assert no `frequency_count` decreased
    - **Validates: Requirements 13.4**

  - [ ] 10.3 Implement `contexta/admin/blueprint_manager.py` — `PromptBlueprintManager`
    - `list_all()`, `activate(blueprint_id)`, `save_new_version(name, version, prompt_text)`, `get_active()`
    - `activate()` delegates to `activate_blueprint()` in repositories, preserving the one-active invariant
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

- [ ] 11. Export and import layer
  - [ ] 11.1 Implement `contexta/export/serializer.py` — `JSONPacketSerializer`
    - `export(packet, output_path)` writes to a `.tmp` file in the same parent directory, then calls `shutil.move(str(tmp_path), str(output_path))` for cross-device-safe atomic rename
    - `shutil.move()` is used instead of `Path.rename()` to prevent `EXDEV` (cross-device link) errors when `/exports` is a Docker volume mount on a different filesystem than `/tmp`
    - On `OSError`, deletes the `.tmp` file if it exists and raises `ExportError` — no partial file is left on disk
    - Raises `ExportError` (wrapping `OSError`) on any filesystem failure
    - Define `ExportError` exception class
    - _Requirements: 11.1, 11.2, 11.3, 11.5_

  - [ ] 11.2 Implement `contexta/export/deserializer.py` — `JSONPacketDeserializer`
    - `import_packet(file_path, conn)`: read file → validate against `JSONPacket` (raise `ImportValidationError` — NO DB write on failure) → write to DB in a single all-or-nothing transaction
    - Define `ImportValidationError` exception class
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [ ]* 11.3 Write property test for JSON export / import round-trip
    - **Property 18: JSON Export / Import Round-Trip** — generate arbitrary complete `JSONPacket` objects; serialise to disk; import via `JSONPacketDeserializer`; assert all `ReviewNodePayload` objects in the resulting `NodeRow` are equivalent to the originals, and `schema_version` is present and non-empty
    - **Validates: Requirements 11.1, 11.2, 12.2, 12.4**

  - [ ]* 11.4 Write property test for import validation — no partial DB write
    - **Property 19: Import Validation — No Partial DB Write** — generate JSON strings that fail `JSONPacket` schema validation; call `import_packet()`; assert `ImportValidationError` is raised and no new rows appear in `nodes`, `projects`, or any other table
    - **Validates: Requirements 12.3**

- [ ] 12. Textual TUI — messages and core widgets
  - [ ] 12.1 Implement `contexta/tui/messages.py` — custom Textual `Message` subclasses
    - `DimensionStateChanged(dimension, state, error)`
    - `ArtifactIngested(artifact)`
    - `AdvisoryAlertDetected(alerts)`
    - `CitationJumpRequested(file_path, line_start, line_end)` — posted by `PipelineView` when an `IssueFinding` is highlighted/selected; carries `file_path`, `line_start`, `line_end` from `finding.citations[0]`
    - _Requirements: 5.5, 5.7, 4.2, 10.8_

  - [ ] 12.2 Implement `contexta/tui/widgets/artifact_view.py` — `ArtifactView` widget
    - Left pane (30% width): `ListView` of ingested files showing filename and line count
    - `TextLog` (scrollable) for file content preview on selection
    - Posts `ArtifactIngested` message on new registration
    - Handles `CitationJumpRequested` messages: on receipt, scrolls the file content preview to bring `line_start` into view and applies a distinct highlight style to all lines in `[line_start, line_end]`
    - Highlight clears when a different finding is selected or the user navigates away
    - _Requirements: 4.2, 4.3, 4.4, 10.2, 10.9_

  - [ ] 12.3 Implement `contexta/tui/widgets/dimension_row.py` — `DimensionRow` widget
    - One instance per `ReviewDimensionEnum`
    - Renders: dimension name label, status badge (PENDING/RUNNING/COMPLETE/FAILED), `ProgressBar` (visible when RUNNING), Retry button (visible when FAILED)
    - Reacts to `DimensionStateChanged` messages to update its display
    - _Requirements: 5.5, 5.6, 5.7_

  - [ ]* 12.4 Write property test for all 12 dimensions represented in status display
    - **Property 12: All 12 Dimensions Represented in Status Display** — mount `PipelineView` in a Textual test runner; assert exactly 12 `DimensionRow` instances are present — one per `ReviewDimensionEnum` value, none missing, none duplicated
    - **Validates: Requirements 5.5**

  - [ ] 12.5 Implement `contexta/tui/widgets/pipeline_view.py` — `PipelineView` widget
    - Right pane (70% width): `MetadataCluster` showing project tags and node info
    - Contains 12 `DimensionRow` instances (one per dimension)
    - `ReconciliationPanel` sub-widget (visible only after Layer 2 completes)
    - Exposes `update_dimension(dimension, state, error)` method
    - _Requirements: 5.5, 6.3, 10.3_

  - [ ] 12.6 Implement `contexta/tui/widgets/modals.py` — all six modal dialogs
    - `ForkNameModal`: text input for node name
    - `ScopeConfirmModal`: explicit acknowledge checkbox before accepting scope change (Req 9.5)
    - `RiskBlockingModal`: displays tag combination, pattern, frequency_count; requires explicit acknowledge button (Req 8.3, 8.4)
    - `CompareBlockingModal`: lists incomplete dimensions, dismiss only (Req 6.5)
    - `ExportConfirmModal`: file path input pre-filled with default export path (Req 11.3)
    - `BlueprintErrorModal`: no active blueprint; dismiss only (Req 14.5)
    - _Requirements: 6.5, 7.3, 8.3, 8.4, 9.5, 11.3, 14.5_

  - [ ]* 12.7 Write property test for citation jump target accuracy
    - **Property 22: Citation Jump Target Accuracy** — for any `IssueFinding` with at least one `SourceCitation`, assert that selecting the finding in `PipelineView` emits a `CitationJumpRequested` message whose `file_path`, `line_start`, and `line_end` exactly match `finding.citations[0]`
    - **Validates: Requirements 10.8, 10.9**

- [ ] 13. Textual TUI — screens and application entry point
  - [ ] 13.1 Implement `contexta/tui/screens/main_screen.py` — `MainScreen`
    - `ContextaHeader` showing current project name, active node name, Admin Tab access indicator
    - Horizontal layout: `ArtifactView` (30%) + `PipelineView` (70%)
    - `ContextaFooter` with labelled keys: `[F] Fork Iteration`, `[C] Compare`, `[P] Run Proposal Generator`, `[E] Export Flat JSON Packet`
    - Footer key bindings respond within 200ms by triggering action or opening modal
    - Full keyboard navigation (no mouse required)
    - Wire `CitationJumpRequested` message flow: when a finding is selected in `PipelineView`, the posted `CitationJumpRequested` is handled by `ArtifactView` to scroll and highlight the target line range (Req 10.8, 10.9)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.8, 10.9_

  - [ ] 13.2 Wire footer key bindings to pipeline actions in `MainScreen`
    - `[F]`: open `ForkNameModal` → on confirm call `fork_node()` → update header node name (Req 7.3, 7.4)
    - `[C]`: check `orchestrator.all_complete()` → if not, open `CompareBlockingModal` listing `incomplete_dimensions()`; if yes, run `ProactiveAdvisor.evaluate()` → if alerts, open `RiskBlockingModal` (record ACK in metadata) → call `ArbitratorEngine.run()` → store synthesis node → show `ReconciliationPanel` (Req 6.1, 6.4, 6.5, 8.2, 8.4, 8.5)
    - `[E]`: open `ExportConfirmModal` → call `JSONPacketSerializer.export()` → show confirmation with file path in footer; on error show error in footer (Req 11.1, 11.4, 11.5)
    - `[P]`: stub handler for Proposal Generator (out of MVP scope; show "not yet implemented" notification)
    - `[Change Scope]` confirmation: after `apply_routing_decision()`, call `apply_mutated_tag()` on active node metadata and display a non-blocking TUI notification: "Scope modified. Consider re-running the Exploration Layer." (Req 9.5)
    - _Requirements: 6.1, 6.5, 7.3, 7.4, 8.2, 8.4, 8.5, 10.4, 10.5, 11.4_

  - [ ] 13.3 Implement node navigation within `MainScreen`
    - Allow keyboard navigation between Nodes for the active project in `PipelineView`
    - On node switch, reload dimension payloads and update header
    - _Requirements: 7.5, 10.7_

  - [ ] 13.4 Implement `contexta/tui/screens/admin_screen.py` — `AdminScreen`
    - `DreamCyclePanel`: trigger button + status indicator (idle/running)
    - `BlueprintPanel`: `DataTable` listing all blueprints with `is_active` indicator; Activate button; New Version button
    - On Dream Cycle trigger, launch `DreamCycleWorker` as a Textual `Worker` (`@work(exclusive=True, thread=False)`)
    - While worker is running, show active status indicator; on completion update sidebar advisory hints
    - On Dream Cycle error, log in Admin Tab panel and terminate worker cleanly (no DB corruption)
    - _Requirements: 13.1, 13.2, 13.3, 13.5, 13.6, 14.1, 14.2, 14.4_

  - [ ] 13.5 Implement `contexta/tui/app.py` — `ContextaApp` (Textual `App` subclass)
    - Holds `DatabaseContext` (single `aiosqlite.Connection`), `ContextaConfig`, `ArtifactRegistry`, `TaskOrchestrator`, `PromptBlueprintManager`
    - Registers `MainScreen` as default and `AdminScreen` as named screen
    - Provides `notify()` for non-fatal errors (timed footer bar)
    - _Requirements: 1.3, 10.1_

  - [ ] 13.6 Implement `contexta/__main__.py` — application entry point
    - Startup sequence: `load_config()` → `init_database()` → construct `ContextaApp` → `app.run_async()`
    - On `ConfigError`, call `show_fatal_error()` TUI overlay and `SystemExit(1)`
    - _Requirements: 1.3, 1.5_

- [ ] 14. Scope Policy UI wiring
  - [ ] 14.1 Wire `ScopePolicyEnforcer` routing toggles into `PipelineView`
    - After Layer 1 completes, call `ScopePolicyEnforcer.get_scope_findings()` on all payloads
    - For each Scope Modification finding, render a routing toggle in the corresponding `DimensionRow` with three options: `[Change Scope]`, `[Route to Risk Register]`, `[Route to Assumptions Matrix]`
    - On `[Change Scope]` selection, open `ScopeConfirmModal`; on acknowledgement call `apply_routing_decision()` with `SCOPE_MODIFICATION`
    - On `[Route to Risk Register]` / `[Route to Assumptions Matrix]`, call `apply_routing_decision()` with appropriate enum value; record in active node `metadata_json` via `write_node`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 15. Checkpoint — TUI and full integration
  - Ensure all tests pass across all layers. Verify the complete end-to-end flow (config → DB init → MCP ingest → Layer 1 run → Layer 2 compare → export) executes correctly in an integration test with mocked LLM and MCP transports. Ask the user if questions arise.

- [ ] 16. Structured JSON import — Admin Tab wiring
  - [ ] 16.1 Wire `JSONPacketDeserializer` into `AdminScreen`
    - Add import JSON command accessible from the Admin Tab
    - On file path submission, call `import_packet()`; on `ImportValidationError` display errors in TUI; on success navigate `PipelineView` to the imported node
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [ ] 17. Final checkpoint — all systems integrated
  - Run the full test suite. Verify property tests, unit tests, and integration tests all pass. Ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery.
- Each task references specific requirements for traceability — use the design document for all interface signatures.
- The 24 correctness properties are distributed across their nearest implementation tasks to catch errors early.
- No task here generates running code for Layer 3 (Decision) or Layer 4 (Learning) — those are Phase 2.
- `[P] Run Proposal Generator` footer key is stubbed in Task 13.2 (Req 10.4 — key must exist) but not fully implemented in MVP.
- All LLM calls in tests should use a mock/stub for `litellm.acompletion` to avoid network dependency.

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["2.4", "2.7"] },
    { "id": 4, "tasks": ["2.5", "2.6"] },
    { "id": 5, "tasks": ["2.8", "3.1", "3.2"] },
    { "id": 6, "tasks": ["3.3"] },
    { "id": 7, "tasks": ["3.4", "3.5", "5.1"] },
    { "id": 8, "tasks": ["5.2", "5.3", "6.1"] },
    { "id": 9, "tasks": ["5.4", "6.2"] },
    { "id": 10, "tasks": ["6.3", "6.4", "7.1"] },
    { "id": 11, "tasks": ["7.2", "7.3"] },
    { "id": 12, "tasks": ["7.4", "7.6", "8.1", "8.3", "8.5"] },
    { "id": 13, "tasks": ["7.5", "8.2", "8.4", "8.6", "10.1", "10.3"] },
    { "id": 14, "tasks": ["10.2", "11.1", "11.2"] },
    { "id": 15, "tasks": ["11.3", "11.4", "12.1"] },
    { "id": 16, "tasks": ["12.2", "12.3"] },
    { "id": 17, "tasks": ["12.4", "12.5"] },
    { "id": 18, "tasks": ["12.6", "12.7", "13.1"] },
    { "id": 19, "tasks": ["13.2", "13.3", "13.4"] },
    { "id": 20, "tasks": ["13.5"] },
    { "id": 21, "tasks": ["13.6", "14.1"] },
    { "id": 22, "tasks": ["16.1"] }
  ]
}
```
