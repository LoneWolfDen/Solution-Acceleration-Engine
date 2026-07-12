# Requirements Document

## Introduction

This document specifies the requirements for a comprehensive audit comparing the original Project Contexta scope against the current state of implementation across the whole codebase, excluding Textual TUI-specific presentation requirements. The audit is triggered by two newly reported symptoms — artifact labels not visible after upload, and missing traceability references from reviews/proposals back to source artifacts — which expand the investigation beyond the previously tracked 11 gaps in `core-scope-gaps-implementation`.

The audit re-uses findings already established for Review Linking and Project-Scoped Proposals (the user's original two reported issues) and re-verifies the remaining items tracked in `core-scope-gaps-implementation`, while additionally walking the full original scope (`.kiro/specs/project-contexta/requirements.md` and `design.md`) end-to-end against the current `contexta/` (backend) and `web/` (Reflex frontend) codebase. The output is a single markdown gap-analysis report — no code changes are made as part of this audit.

---

## Glossary

- **Audit**: The comprehensive investigative activity specified by this document, comparing original scope to current implementation.
- **Audit_Report**: The single markdown deliverable file produced by the Audit, containing all Gap_Item entries in list format with reasoning.
- **Original_Scope_Document**: The pair of files `.kiro/specs/project-contexta/requirements.md` and `.kiro/specs/project-contexta/design.md`, treated as the source of truth for intended functionality.
- **Web_Scope**: The subset of Original_Scope_Document acceptance criteria that describe functional intent realizable through the web/API layer (`contexta/api/`, `contexta/pipeline/`, `contexta/db/`, `web/`), excluding any acceptance criterion whose behavior is defined purely in terms of Textual TUI mechanics (keyboard-only navigation, footer key bindings, TUI pane layout, `CitationJumpRequested` message handling, Admin Tab screen navigation).
- **Gap_Item**: A single audited unit of scope (one Original_Scope_Document requirement, sub-criterion, or reported symptom) recorded in the Audit_Report with a Status_Classification and supporting reasoning.
- **Status_Classification**: The classification assigned to a Gap_Item, taking exactly one of four values: `Not_Implemented`, `Implemented_Not_Wired`, `Implemented_Differently`, or `Fully_Implemented`.
- **Core_Gaps_Spec**: The existing spec at `.kiro/specs/core-scope-gaps-implementation/` (requirements.md, design.md, tasks.md) documenting 11 previously identified gaps.
- **Artifact_Labeling_Finding**: The Gap_Item addressing the reported symptom that labels/tags/metadata are not visible after an artifact is uploaded.
- **Artifact_Traceability_Finding**: The Gap_Item addressing the reported symptom that reviews, proposals, and other entities lack visible reference links back to the source artifacts they cite.
- **Review_Linking_Finding**: The Gap_Item addressing the user's originally reported issue of selecting previous reviews when creating a new review.
- **Project_Scoped_Proposal_Finding**: The Gap_Item addressing the user's originally reported issue that proposals should be selectable across all reviews/versions under a project rather than scoped to one review/version.
- **Tracking_Gap**: The Gap_Item flagging that `core-scope-gaps-implementation/tasks.md` shows all checkboxes unchecked despite evidence of partial or complete implementation.
- **Scripts_Markdown_Note**: The Gap_Item recording that the `/scripts` directory contains no markdown files for review.

---

## Requirements

### Requirement 1 — Audit Scope Coverage

**User Story:** As a project stakeholder, I want the audit to cover every non-TUI functional area defined in the original Project Contexta scope, so that no implementation gap is missed because it fell outside the previously tracked 11-gap checklist.

#### Acceptance Criteria

1. THE Audit SHALL evaluate every Web_Scope acceptance criterion derived from Original_Scope_Document Requirements 1 through 14.
2. THE Audit SHALL exclude from evaluation any acceptance criterion whose behavior is defined exclusively in terms of Textual TUI rendering, TUI keyboard navigation, or TUI-specific message classes (`CitationJumpRequested`, footer key bindings, TUI pane layout).
3. WHERE an Original_Scope_Document requirement mixes TUI-specific mechanics with a web-realizable functional intent (e.g. Fork, Compare, Export, Admin Tab actions), THE Audit SHALL evaluate the web-realizable functional intent as part of Web_Scope while noting the TUI-only portion as excluded.
4. THE Audit SHALL include, as a subset of its Gap_Item set, re-verification of all 11 gaps previously documented in Core_Gaps_Spec rather than assuming their prior documented status remains accurate.
5. THE Audit SHALL record the Review_Linking_Finding and the Project_Scoped_Proposal_Finding as explicitly labeled Gap_Item entries corresponding to the user's originally reported issues.
6. THE Audit SHALL record the Artifact_Labeling_Finding and the Artifact_Traceability_Finding as explicitly labeled Gap_Item entries corresponding to the user's newly reported symptoms.

---

### Requirement 2 — Status Classification Criteria

**User Story:** As a project stakeholder, I want every audited scope item classified using consistent, well-defined criteria, so that I can distinguish missing work from work that exists but is not surfaced to users.

#### Acceptance Criteria

1. THE Audit SHALL assign exactly one Status_Classification value to each Gap_Item.
2. THE Audit SHALL assign `Not_Implemented` WHEN no corresponding backend code, API endpoint, database schema, or UI component exists for the audited scope item.
3. THE Audit SHALL assign `Implemented_Not_Wired` WHEN backend code, an API endpoint, or a UI component exists for the audited scope item but is not imported, rendered, called, or reachable from any active user flow.
4. THE Audit SHALL assign `Implemented_Differently` WHEN the audited scope item is realized through a mechanism, data model, or scope boundary that diverges from the Original_Scope_Document description (e.g. per-version scoping instead of per-project scoping).
5. THE Audit SHALL assign `Fully_Implemented` WHEN the audited scope item has backend support, API exposure, and a UI path that a user can reach and observe without additional wiring.
6. FOR each Gap_Item, THE Audit_Report SHALL include a reasoning statement citing the specific file paths and code constructs examined to justify the assigned Status_Classification.

---

### Requirement 3 — Review Linking and Project-Scoped Proposal Findings

**User Story:** As the user who originally reported these two issues, I want the audit to explicitly confirm root cause and current status for review linking and project-scoped proposals, so that I know whether these are backend gaps, UI wiring gaps, or scope-boundary mismatches.

#### Acceptance Criteria

1. THE Audit_Report SHALL classify the Review_Linking_Finding as `Implemented_Not_Wired`, citing the disabled `rx.cond` block in `web/pages/run_review.py` and the existing but unused `web/components/review_link_selector.py` component as evidence.
2. THE Audit_Report SHALL document that backend support for review linking — the `review_links` table, `POST /api/reviews` accepting `linked_review_ids`, and `GET /api/versions/{id}/reviews/linkable` — is present and functional.
3. THE Audit_Report SHALL classify the Project_Scoped_Proposal_Finding as `Implemented_Differently`, citing that proposal endpoints in `contexta/api/routers/proposals.py` scope aggregation to a single version rather than across all versions of a project.
4. THE Audit_Report SHALL document that the version-level proposal UI (`web/components/proposal_form.py` and `proposals_list()`) exists but is never imported or rendered in `web/components/version_detail.py`, and SHALL classify this UI absence as a contributing `Implemented_Not_Wired` factor of the Project_Scoped_Proposal_Finding.

---

### Requirement 4 — Artifact Labeling Investigation

**User Story:** As the user who reported that artifact labels are not visible after upload, I want the audit to trace the label/tag data path from upload through storage to every UI surface, so that I know exactly where visibility breaks down, if at all.

#### Acceptance Criteria

1. THE Audit SHALL trace the artifact tag/label data path across `contexta/api/routers/artifacts.py`, `contexta/api/repositories.py`, `contexta/api/schemas.py`, `web/components/ingestion_modal.py`, `web/components/triage_widget.py`, and `web/components/version_detail.py`.
2. THE Audit_Report SHALL document, for each surface in the traced path, whether tag/label data is persisted, returned by the API, and rendered in the corresponding UI component.
3. IF the Audit finds that tag/label data is persisted and returned by the API but not rendered in one or more UI surfaces, THEN THE Audit_Report SHALL classify the Artifact_Labeling_Finding as `Implemented_Not_Wired` for that surface and identify the specific component and missing render call.
4. IF the Audit finds that tag/label data is rendered correctly in all traced UI surfaces under static code inspection, THEN THE Audit_Report SHALL state this explicitly and flag the discrepancy with the user's reported symptom as requiring runtime/browser verification beyond static code review.
5. THE Audit_Report SHALL record the Artifact_Labeling_Finding as a distinct, clearly labeled Gap_Item regardless of its assigned Status_Classification.

---

### Requirement 5 — Artifact Traceability Investigation

**User Story:** As the user who reported missing traceability references, I want the audit to determine whether reviews, proposals, and other entities expose their links back to source artifacts anywhere in the UI, so that I know whether this is a missing feature or a missing UI surface for existing data.

#### Acceptance Criteria

1. THE Audit SHALL trace citation and provenance data from `contexta/models/citations.py` (`SourceCitation.file_path`) through `contexta/api/routers/reviews.py` (`FindingItem.source_artifact`, `FindingItem.citation`) to `web/components/finding_card.py`.
2. THE Audit_Report SHALL document whether `FindingItem.source_artifact` and `FindingItem.citation` are populated with real artifact references and whether they are rendered in the finding display.
3. THE Audit SHALL determine whether any UI surface allows navigation from a rendered citation or source-artifact reference back to the originating artifact's content or triage entry.
4. IF no UI surface provides artifact-level provenance navigation (as opposed to a plain text label), THEN THE Audit_Report SHALL classify the Artifact_Traceability_Finding as `Not_Implemented` or `Implemented_Differently` as appropriate, with reasoning distinguishing "citation text is shown" from "citation is a navigable, traceable reference."
5. THE Audit SHALL determine whether artifact-version links (`artifact_version_links` table, `current_version_artifacts` in `web/state.py`) are exposed anywhere that connects a review's findings back to which artifacts were active for that specific review run.
6. THE Audit_Report SHALL record the Artifact_Traceability_Finding as a distinct, clearly labeled Gap_Item regardless of its assigned Status_Classification.

---

### Requirement 6 — Re-verification of Previously Documented Gaps

**User Story:** As a project stakeholder, I want the previously documented 11 gaps re-verified rather than copied forward unchanged, so that the audit reflects the codebase's actual current state.

#### Acceptance Criteria

1. THE Audit SHALL re-verify the current implementation status of each of the 11 gaps documented in Core_Gaps_Spec: Fork, Proactive Advisor, Scope Policy UI, JSON Export, JSON Import, Dream Cycle, Blueprint Management, Insights Sidebar, Version-Level Proposal Listing, Review Linking, and Proposal Re-Architecture.
2. FOR each of the 11 gaps, THE Audit_Report SHALL state whether the Status_Classification recorded in Core_Gaps_Spec (implicitly "not implemented" for all, per its unchecked tasks.md) still holds or has changed based on current code inspection.
3. WHERE the Audit finds a gap's backend or UI code exists but Core_Gaps_Spec `tasks.md` still shows its corresponding task as unchecked, THE Audit_Report SHALL note this discrepancy as part of the Tracking_Gap.

---

### Requirement 7 — Tracking and Documentation Gap

**User Story:** As a project stakeholder, I want the audit to flag inconsistency between the task tracker and actual code state, so that the tracked task list can be trusted going forward.

#### Acceptance Criteria

1. THE Audit_Report SHALL record the Tracking_Gap as a distinct Gap_Item, citing that `.kiro/specs/core-scope-gaps-implementation/tasks.md` shows all checkboxes unchecked despite code evidence of partial or complete implementation for multiple gaps.
2. THE Audit_Report SHALL list which specific tasks in `tasks.md` appear inconsistent with the current code state, based on the Audit's own re-verification in Requirement 6.

---

### Requirement 8 — Scripts Directory Markdown Note

**User Story:** As the user who originally asked for a review of markdown files in `/scripts`, I want the audit to confirm the absence of such files rather than silently drop the request, so that I have closure on that part of my original ask.

#### Acceptance Criteria

1. THE Audit_Report SHALL record the Scripts_Markdown_Note stating that `/scripts` contains no markdown files, listing the actual contents (`dev-start.sh`, `healthcheck.sh`, `init_db.py`) found during investigation.

---

### Requirement 9 — Audit Deliverable Format

**User Story:** As a project stakeholder, I want the audit output delivered as a single, clearly organized markdown file, so that I can review all findings in one place without cross-referencing multiple documents.

#### Acceptance Criteria

1. THE Audit SHALL produce exactly one markdown file as the Audit_Report, containing all Gap_Item entries organized in a clear list format grouped by functional area.
2. FOR each Gap_Item, THE Audit_Report SHALL include: a short title, the Status_Classification, the reasoning with cited file paths, and a reference back to the originating Original_Scope_Document requirement number or reported symptom.
3. THE Audit_Report SHALL include a dedicated section explicitly presenting the Review_Linking_Finding and the Project_Scoped_Proposal_Finding as resolutions to the user's originally reported issues.
4. THE Audit_Report SHALL include a dedicated section explicitly presenting the Artifact_Labeling_Finding and the Artifact_Traceability_Finding as resolutions to the user's newly reported symptoms.
5. THE Audit_Report SHALL include the Tracking_Gap and the Scripts_Markdown_Note as explicitly labeled sections distinct from the functional Gap_Item list.
6. THE Audit SHALL NOT modify any source code, configuration, or existing spec files as part of producing the Audit_Report.
