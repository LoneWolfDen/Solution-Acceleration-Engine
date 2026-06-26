# Requirements Document

## Introduction

The **TUI IDE Interface** is a new screen for the Solution-Acceleration-Engine (Contexta) that provides an "IDE for Project Delivery" reading experience in the terminal. The interface lets users navigate the full project data hierarchy — Projects → Versions → Reviews → Proposals — and read text-rich content comfortably without leaving the terminal.

The navigation sidebar uses a VS Code-inspired file-explorer tree. The content area and all other chrome are designed from first principles for **text-heavy reading**: generous padding, restrained decoration, clear typographic hierarchy, and calm colour use — optimised for long reading sessions by non-technical users. A persistent status bar surfaces delivery confidence and gate status at a glance.

The TUI layer is strictly presentation-only. All data retrieval and serialisation is handled by a thin `Preview_Controller` that bridges the existing backend. No business logic resides in TUI widgets.

This feature is additive: the existing `MainScreen` and pipeline flow are unchanged; 596+ existing tests must continue to pass.

---

## Glossary

- **Preview_Screen**: The new Textual `Screen` subclass implementing the IDE-style interface, at `contexta/tui/screens/preview_screen.py`.
- **Project_Tree**: The VS Code-inspired collapsible tree sidebar widget for navigating the project data hierarchy.
- **Tree_Node**: A selectable, typed entry in the Project_Tree — one of: Project, Version, Review, Proposal, or Prompt.
- **Content_Pane**: The main reading area occupying the majority of screen width; renders structured content for the selected Tree_Node with comfortable padding and scrolling.
- **Content_Tab**: A named tab within the Content_Pane — currently: "Findings", "Proposal", and "Prompt".
- **Status_Bar**: A single persistent line at the bottom of the Preview_Screen showing Gate_Status and Delivery_Confidence_Score for the currently selected Review Tree_Node.
- **Preview_Controller**: The thin backend adapter at `contexta/tui/preview_controller.py` that the Preview_Screen calls to fetch data; contains no TUI code and no UI-layer computation beyond data retrieval and serialisation.
- **Node_Payload**: A JSON-serialisable Python `dataclass` returned by the Preview_Controller for a selected Tree_Node; schema varies by node type.
- **Project_Payload**: A Node_Payload for a Project — fields: `id`, `name`, `global_tags`, `version_ids`.
- **Version_Payload**: A Node_Payload for a Version — fields: `id`, `project_id`, `name`, `created_at`, `node_ids`.
- **Review_Payload**: A Node_Payload for a Review node — fields: `id`, `node_name`, `layer_type`, `findings`, `gate_status`, `delivery_confidence_score`, `prompt_text`.
- **Proposal_Payload**: A Node_Payload for a Proposal leaf — fields: `id`, `node_id`, `content_markdown`.
- **Prompt_Payload**: A Node_Payload for a Prompt leaf — fields: `id`, `node_id`, `prompt_text`.
- **Risk_Highlight**: The visual style applied to finding rows where confidence is RED or AMBER — foreground-only coloured text (red for RED findings, amber for AMBER findings) against the default background, keeping the aesthetic lightweight.
- **Gate_Status**: A string value ("PASS", "WARN", or "FAIL") derived from the `overall_confidence` of the stored `ReviewNodePayload` via a static, side-effect-free mapping: GREEN → PASS, AMBER → WARN, RED → FAIL.
- **Delivery_Confidence_Score**: An integer percentage (0–100), truncated toward zero, representing the proportion of `IssueFinding` items with `ConfidenceEnum.GREEN` confidence relative to all findings in a Review_Payload. Returns 0 when no findings exist.
- **Docker_Compose_Config**: The `docker-compose.yml` file added to the repository root that provides zero-install container orchestration.
- **Test_Suite**: The 596 or more existing pytest tests in the `tests/` directory.

---

## Requirements

### Requirement 1: Project Navigation Tree View

**User Story:** As a project delivery professional, I want to navigate my projects, versions, reviews, and proposals through a collapsible tree sidebar, so that I can quickly locate any piece of project content without memorising IDs or paths.

#### Acceptance Criteria

1. WHEN the Preview_Screen mounts, THE Project_Tree SHALL load all projects from the Preview_Controller and display them as root-level expandable nodes.
2. WHEN a Project Tree_Node is expanded by the user, THE Project_Tree SHALL display its associated versions as immediate child nodes.
3. WHEN a Version Tree_Node is expanded by the user, THE Project_Tree SHALL display its associated Review Tree_Nodes as immediate child nodes.
4. WHEN a Review Tree_Node is expanded, IF a Proposal_Payload exists for that node, THE Project_Tree SHALL display a "Proposal" leaf Tree_Node as a child of that Review Tree_Node.
5. WHEN a Review Tree_Node is expanded, IF a Prompt_Payload exists for that node, THE Project_Tree SHALL display a "Prompt" leaf Tree_Node as a child of that Review Tree_Node.
6. WHEN a Tree_Node is collapsed, THE Project_Tree SHALL hide all descendant nodes and retain the expanded or collapsed state of each descendant so that re-expanding the node restores the prior subtree view.
7. THE Project_Tree SHALL visually distinguish each Tree_Node type using a fixed prefix: `[P]` for Project, `[V]` for Version, `[R]` for Review, `[D]` for Proposal, and `[T]` for Prompt — using characters compatible with all terminal fonts.
8. WHEN a Tree_Node is selected via keyboard navigation or pointer, THE Project_Tree SHALL apply an inverted-color highlight to the selected row and emit a selection event carrying the Tree_Node type and unique identifier to the Preview_Screen.
9. WHILE the Project_Tree is loading data from the Preview_Controller, THE Project_Tree SHALL display a single-line "Loading projects…" indicator in place of the tree content.
10. IF the Preview_Controller returns an empty project list, THEN THE Project_Tree SHALL display a static "No projects found. Run a review to get started." message.
11. IF the Preview_Controller fails to return project data, THEN THE Project_Tree SHALL replace the loading indicator with a single-line error message indicating that projects could not be loaded.

---

### Requirement 2: Content Reader Pane

**User Story:** As a project delivery professional, I want to read project findings, proposal text, and generation prompts in a well-padded, calm main panel, so that I can review lengthy text content without visual fatigue or clutter.

#### Acceptance Criteria

1. WHEN a Review Tree_Node is selected and its Review_Payload is loaded, THE Content_Pane SHALL display a tab bar showing three Content_Tabs — "Findings" (default active), "Proposal", and "Prompt" — for that node.
2. WHILE the "Findings" Content_Tab is active, THE Content_Pane SHALL render each `IssueFinding` as a structured row showing its dimension label, confidence badge, summary line, and detail text — separated by a horizontal rule.
3. IF a finding's confidence value is RED, THE Content_Pane SHALL render that finding's dimension label and confidence badge in red-coloured foreground text. IF a finding's confidence value is AMBER, THE Content_Pane SHALL render that finding's dimension label and confidence badge in amber-coloured foreground text.
4. WHILE the "Proposal" Content_Tab is active, IF the Review_Payload contains non-empty `content_markdown`, THE Content_Pane SHALL render the markdown as formatted text using Textual's `Markdown` widget.
5. WHILE the "Proposal" Content_Tab is active, IF `content_markdown` is empty or contains only whitespace, THE Content_Pane SHALL display a "No proposal generated for this review." placeholder message.
6. WHILE the "Prompt" Content_Tab is active, THE Content_Pane SHALL display the `prompt_text` string in a monospace-styled scrollable text area.
7. THE Content_Pane SHALL be independently scrollable within its own pane boundaries for all Content_Tab views.
8. WHEN a Project or Version Tree_Node is selected, THE Content_Pane SHALL display a summary card showing the node's name, type label, creation timestamp (or "N/A" if not available), and a bulleted list of immediate child node names (or "No items" if none exist).
9. WHILE no Tree_Node is selected, THE Content_Pane SHALL display a static welcome card listing the available keyboard navigation shortcuts.
10. WHILE the Preview_Controller is fetching a Node_Payload, THE Content_Pane SHALL replace the main content area with a single-line "Fetching…" indicator.
11. IF the Preview_Controller raises an exception during a data fetch, THEN THE Content_Pane SHALL display a message indicating the failure reason in red-highlighted style; IF previously displayed content exists, it SHALL remain visible at reduced opacity; IF no previous content exists, the pane SHALL display only the error message.

---

### Requirement 3: Status Bar

**User Story:** As a project delivery professional, I want a persistent status bar at the bottom of the screen showing the gate status and delivery confidence score for the active review, so that I can assess project health at a glance without switching context.

#### Acceptance Criteria

1. WHEN a Review Tree_Node is selected and its Review_Payload is loaded, THE Status_Bar SHALL display the Gate_Status value for that node.
2. WHEN a Review Tree_Node is selected and its Review_Payload is loaded, THE Status_Bar SHALL display the Delivery_Confidence_Score as an integer percentage immediately after the Gate_Status.
3. WHEN Gate_Status is "PASS", THE Status_Bar SHALL render the status indicator in green-coloured style.
4. WHEN Gate_Status is "WARN", THE Status_Bar SHALL render the status indicator in amber-coloured style.
5. WHEN Gate_Status is "FAIL", THE Status_Bar SHALL render the status indicator in red-coloured style.
6. WHEN no Review Tree_Node is selected, THE Status_Bar SHALL display "— No node selected —" with neutral (default) styling.
7. THE Status_Bar SHALL remain visible at the bottom of the Preview_Screen at all times, regardless of Content_Pane scroll position or active Content_Tab.

---

### Requirement 4: Controller API Contract

**User Story:** As a developer, I want a clean, JSON-serialisable contract between the TUI layer and the backend services, so that the Preview_Screen can be tested in isolation and the backend can evolve without touching TUI code.

#### Acceptance Criteria

1. THE Preview_Controller SHALL expose a `list_projects()` async method returning a list of `Project_Payload` objects.
2. THE Preview_Controller SHALL expose a `get_version_payload(version_id: str)` async method returning a `Version_Payload` or `None`.
3. THE Preview_Controller SHALL expose a `get_review_payload(node_id: str)` async method returning a `Review_Payload` or `None`.
4. THE Preview_Controller SHALL expose a `get_proposal_payload(node_id: str)` async method returning a `Proposal_Payload` or `None`.
5. THE Preview_Controller SHALL expose a `get_prompt_payload(node_id: str)` async method returning a `Prompt_Payload` or `None`.
6. WHEN a requested entity does not exist in the database, THE Preview_Controller SHALL return `None` rather than raising an exception.
7. THE Preview_Controller SHALL derive Gate_Status from the `overall_confidence` field of the stored `ReviewNodePayload` by applying a static, side-effect-free mapping where each `ConfidenceEnum` value maps to exactly one Gate_Status value, without performing LLM calls or external I/O.
8. THE Preview_Controller SHALL derive Delivery_Confidence_Score by computing the integer percentage, truncated toward zero, of `IssueFinding` items with `confidence == ConfidenceEnum.GREEN` out of the total `IssueFinding` count in the stored `ReviewNodePayload`.
9. THE Preview_Controller SHALL accept an `aiosqlite.Connection` as its sole external dependency, injected at construction time, and SHALL NOT open or close database connections itself.
10. THE Preview_Controller SHALL ensure that any `Review_Payload` returned by `get_review_payload()` satisfies the round-trip property: serialising the payload to a JSON string and deserialising it back SHALL produce an object where every field contains a value identical to the original, with no field absent or changed to `None` that was non-`None` in the original.
11. IF the stored `ReviewNodePayload` contains zero `IssueFinding` items, THEN THE Preview_Controller SHALL return a Delivery_Confidence_Score of 0.
12. IF a database operation raises an exception during execution of any Preview_Controller method, THEN THE Preview_Controller SHALL propagate the exception to the caller without modification and SHALL NOT return `None` in place of the exception.

---

### Requirement 5: Dumb TUI Layer

**User Story:** As a developer, I want the TUI layer to contain zero business logic, so that the interface remains independently testable, maintainable, and decoupled from backend implementation details.

#### Acceptance Criteria

1. THE Preview_Screen SHALL delegate all data retrieval exclusively to the Preview_Controller and SHALL NOT directly access `aiosqlite`, `contexta.db`, or any submodule within `contexta.db` at runtime.
2. THE Preview_Screen widgets SHALL display Gate_Status, Delivery_Confidence_Score, and Risk_Highlight flags using values provided by the Preview_Controller without recomputing these values from raw pipeline or database data.
3. THE Preview_Screen SHALL contain no static or dynamic imports from `contexta.pipeline`, `contexta.llm`, or `contexta.admin`.
4. WHEN the Preview_Controller returns `None` for a requested payload, THE Preview_Screen SHALL render a visible empty-state indicator in place of the payload content without raising an exception.
5. THE Preview_Screen SHALL be unit-testable by injecting a stub object that implements the same async method signatures as the Preview_Controller, returning pre-built Node_Payload instances.
6. IF the Preview_Controller raises an exception during data retrieval, THEN THE Preview_Screen SHALL display an error-state indicator without propagating the exception to the Textual application event loop.

---

### Requirement 6: Docker Compose Configuration

**User Story:** As a non-technical user, I want to run the full application with a single command from any machine with Docker installed, so that I can use Contexta without installing Python, managing dependencies, or configuring an environment.

#### Acceptance Criteria

1. THE Docker_Compose_Config SHALL define a single service named `contexta` that builds from the existing `Dockerfile` at the repository root.
2. THE Docker_Compose_Config SHALL declare a named volume `contexta_data` and mount it at `/data` inside the `contexta` service container.
3. THE Docker_Compose_Config SHALL declare a named volume `contexta_exports` and mount it at `/exports` inside the `contexta` service container.
4. THE Docker_Compose_Config SHALL set `stdin_open: true` and `tty: true` on the `contexta` service to enable terminal interaction.
5. WHEN `docker compose up` is executed in the repository root with all required environment variables set, THE Docker_Container SHALL launch the Contexta TUI and present it ready for user input, without requiring Python installation, virtual environment setup, or package installation on the host machine.
6. THE Docker_Compose_Config SHALL include an `environment` block listing the required variable `CONTEXTA_LLM_BACKEND` and optional variables `CONTEXTA_DB_PATH`, `CONTEXTA_EXPORT_PATH`, and `CONTEXTA_LOG_LEVEL`, each with an example placeholder value that illustrates the expected format (using `/data` for `CONTEXTA_DB_PATH`, `/exports` for `CONTEXTA_EXPORT_PATH`, and `INFO` for `CONTEXTA_LOG_LEVEL`) and an inline YAML comment explaining each variable's purpose.
7. IF `CONTEXTA_LLM_BACKEND` is absent or empty at container start, THEN THE Docker_Container SHALL start successfully and display a warning message indicating that the LLM backend is not configured and that LLM-dependent features will be unavailable, rather than raising an unhandled exception.

---

### Requirement 7: Test Suite Compatibility

**User Story:** As a developer, I want the new TUI IDE interface feature to integrate cleanly with the existing codebase, so that the CI pipeline remains green and no regressions are introduced to the 596+ passing tests.

#### Acceptance Criteria

1. WHEN the `Preview_Screen` and `Preview_Controller` modules are added to the codebase, THE Test_Suite SHALL continue to pass all 596 or more existing tests without any changes to files under the `tests/` directory.
2. THE `pyproject.toml` `[tool.coverage.run]` `omit` list SHALL include a pattern that excludes `contexta/tui/preview_controller.py` from coverage measurement — either by adding an explicit entry for that file path or by verifying that the existing `contexta/tui/*` glob pattern matches all files recursively under `contexta/tui/` — such that the overall reported project coverage score remains at or above 90% after the feature is merged.
3. THE `Preview_Screen` module SHALL contain no top-level import statements for `contexta.pipeline`, `contexta.llm`, or `contexta.admin`, such that executing `import contexta.tui.screens.preview_screen` in a Python interpreter triggers none of those packages' module-level initialisation code.
4. WHEN `pytest tests/` is executed after this feature is merged, THE Test_Runner SHALL exit with exit code 0, with zero test items reported as `ERROR` or `FAILED` in the final session summary line.
