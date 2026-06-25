# Kiro Engineering Manifesto: "The Engine First"

1. **Hierarchy Before UI:** The TUI is a read-only projection. Logic exists in `contexta/pipeline/` or `contexta/services/`.
2. **Deterministic Provenance:** If a function lacks a `provenance_id` (linking to an Artifact paragraph/slide), it is incomplete.
3. **The Veto Criteria (Validation Gate):** - **Traceability Density:** Claims without `[ArtifactID:SectionID]` are "Unsubstantiated."
    - **Contradiction Check:** Output must be compared against `knowledge_observations`.
    - **Multi-Dimensional Coverage:** All 12 dimensions must be addressed; filler text is "Insufficient Depth."
    - **Diagram Alignment:** All `draw.io` artifacts must be supported by text rationale.
4. **Judge-in-the-Loop:** All proposals must be validated by the `ArbitratorEngine` acting as a Judge. If Veto criteria are met, reject and regenerate.
