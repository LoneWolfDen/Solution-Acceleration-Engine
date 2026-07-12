"""
web/components/scope_policy_panel.py — Scope Policy Panel (Gap 5).

Displays scope-modification findings with routing toggle buttons
and records routing decisions via the /api/nodes/{node_id}/routing-decision
endpoint.
"""

import reflex as rx

from web.state import AppState


def _finding_row(finding: dict) -> rx.Component:
    """A single finding row with routing decision buttons."""
    # Latest routing decision label for this finding, keyed by finding_id in
    # a typed dict[str, str] computed var (this Reflex version's ArrayVar has
    # no `.filter()` method, so the lookup + label mapping is pre-computed
    # server-side and consumed here via compile-safe `.contains()`/`[...]`).
    finding_id = finding["finding_id"].to(str)
    has_decision = AppState.routing_decision_label_by_finding.contains(finding_id)
    decision_label = AppState.routing_decision_label_by_finding.get(finding_id, "")

    return rx.vstack(
        rx.hstack(
            rx.icon(rx.cond(finding["severity"] == "HIGH", "triangle-alert", "info"), size=16, color="var(--gray-9)"),
            rx.vstack(
                rx.text(finding["type"], size="2", weight="medium"),
                rx.text(finding["text"], size="2", color_scheme="gray"),
                spacing="0",
                align="start",
            ),
            rx.spacer(),
            rx.cond(
                finding["type"] == "Scope Modification",
                rx.hstack(
                    rx.badge(
                        "Scope Mod",
                        color_scheme="amber",
                        variant="soft",
                        size="1",
                    ),
                    rx.cond(
                        # Check if this finding_id has been routed
                        has_decision,
                        rx.badge(
                            decision_label,
                            color_scheme="green",
                            variant="soft",
                            size="1",
                        ),
                        rx.cond(
                            AppState.routing_edit_mode,
                            rx.select.root(
                                rx.select.trigger(width="140px", size="1"),
                                rx.select.content(
                                    rx.select.item("Route to Risk Register", value="risk_register"),
                                    rx.select.item("Route to Assumptions Matrix", value="assumptions_matrix"),
                                    rx.select.item("Approve Scope Modification", value="scope_modification"),
                                ),
                                value=AppState._routing_decision_value,
                                on_change=AppState.set_routing_decision_value,
                            ),
                            rx.text("", width="0"),
                        ),
                    ),
                    rx.button(
                        "Record",
                        size="1",
                        variant="soft",
                        color_scheme="indigo",
                        disabled=~AppState.routing_edit_mode,
                        on_click=AppState.submit_routing_decision(
                            AppState.selected_node_id,
                            finding["finding_id"],
                            AppState._routing_decision_value,
                            AppState._routing_decision_acknowledged,
                        ),
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.text("", width="0"),
            ),
            spacing="3",
            align="center",
            width="100%",
        ),
        padding="0.75rem",
        background="var(--gray-2)",
        border="1px solid var(--gray-4)",
        border_radius="6px",
        width="100%",
    )


def scope_policy_panel() -> rx.Component:
    """Panel for scope policy enforcement and routing decisions.
    
    Gap 5 — Requirements 5.1-5.6: highlights scope-modification
    findings, displays routing toggle buttons, records routing
    decisions via /api/nodes/{node_id}/routing-decision.
    """
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("shield-alert", size=16, color="var(--gray-9)"),
                rx.text("Scope Policy Enforcement", size="2", weight="medium"),
                rx.spacer(),
                rx.button(
                    rx.cond(
                        AppState.routing_edit_mode,
                        "Cancel",
                        "Edit Routing",
                    ),
                    size="2",
                    variant="soft",
                    color_scheme="indigo",
                    on_click=AppState.toggle_routing_edit,
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            rx.divider(width="100%"),
            rx.cond(
                AppState.current_findings.length() > 0,
                rx.vstack(
                    rx.foreach(
                        AppState.current_findings,
                        _finding_row,
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.text(
                    "No findings to review.",
                    size="2",
                    color_scheme="gray",
                ),
            ),
            spacing="3",
            width="100%",
        ),
        width="100%",
        padding="1.5rem",
        background="var(--gray-1)",
        border="1px solid var(--gray-4)",
        border_radius="12px",
    )
