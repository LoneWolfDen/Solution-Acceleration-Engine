"""contexta/services — Orchestration service layer.

Services sit between the TUI/CLI entry points and the pipeline/DB modules.
Each service owns a single concern: fetching data, applying guards, and
delegating to the relevant engine.
"""
