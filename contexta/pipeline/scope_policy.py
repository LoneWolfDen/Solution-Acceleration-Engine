"""Pipeline — Unalterable Scope Policy enforcement.

Design contracts
----------------
- ``ScopePolicyEnforcer.get_scope_findings()`` filters all
  ``IssueFinding`` objects across all payloads where
  ``mitigation_routing == MitigationRoutingEnum.SCOPE_MODIFICATION``.
  The original payload list is never mutated.

- ``ScopePolicyEnforcer.apply_routing_decision()`` records the routing
  decision **permanently** in ``metadata["routing_decisions"]``.  This key
  is created if absent.  The updated ``metadata`` dict is returned; the
  caller is responsible for persisting it via ``write_node()``.

- When the user selects ``Scope Modification`` as the routing decision
  (i.e. ``decision == MitigationRoutingEnum.SCOPE_MODIFICATION``), the
  string ``"#MUTATED"`` is appended to ``metadata["tags"]`` (created as an
  empty list if absent).  This tag is permanent and is never removed by
  this module.

- Property 17 (Scope Policy Routing Decision Persistence) asserts:
  for any ``IssueFinding`` with ``SCOPE_MODIFICATION`` routing and any
  valid ``MitigationRoutingEnum`` decision, the returned metadata contains
  a ``routing_decisions`` entry whose ``new_routing`` equals
  ``decision.value``.
"""

from __future__ import annotations

from typing import Dict, List

from ..models.enums import MitigationRoutingEnum
from ..models.findings import IssueFinding
from ..models.payloads import ReviewNodePayload

_MUTATED_TAG: str = "#MUTATED"


class ScopePolicyEnforcer:
    """Detects and routes ``Scope Modification`` findings.

    This class is stateless — instantiate once and call methods as needed.
    All state is stored in the ``metadata`` dict that callers own.
    """

    # ── Query ──────────────────────────────────────────────────────────────────

    def get_scope_findings(
        self,
        payloads: List[ReviewNodePayload],
    ) -> List[IssueFinding]:
        """Return all findings with ``mitigation_routing == SCOPE_MODIFICATION``.

        Iterates all payloads and all findings within each payload.  The
        original ``payloads`` list is never mutated.

        Parameters
        ----------
        payloads:
            Any collection of ``ReviewNodePayload`` objects (typically the
            12 completed Layer 1 payloads).

        Returns
        -------
        List[IssueFinding]
            Flat list of matching findings across all payloads.  Empty list
            if no ``SCOPE_MODIFICATION`` findings exist.
        """
        findings: List[IssueFinding] = []
        for payload in payloads:
            for finding in payload.findings:
                if finding.mitigation_routing == MitigationRoutingEnum.SCOPE_MODIFICATION:
                    findings.append(finding)
        return findings

    # ── Mutation ───────────────────────────────────────────────────────────────

    def apply_routing_decision(
        self,
        finding: IssueFinding,
        decision: MitigationRoutingEnum,
        metadata: Dict,
    ) -> Dict:
        """Record a routing decision permanently in ``metadata``.

        Appends a new entry to ``metadata["routing_decisions"]``.  If the
        key is absent it is initialised to an empty list first — existing
        entries are never overwritten.

        If ``decision == MitigationRoutingEnum.SCOPE_MODIFICATION``, the
        ``"#MUTATED"`` tag is appended to ``metadata["tags"]`` (creating
        the list if necessary).  This marks the node as having accepted a
        scope change and is visible to the TUI and export layer.

        Parameters
        ----------
        finding:
            The ``IssueFinding`` being routed.
        decision:
            The user-selected ``MitigationRoutingEnum`` value.
        metadata:
            The mutable metadata dict for the active node.  This dict is
            modified **in place** and also returned for convenience.

        Returns
        -------
        Dict
            The updated ``metadata`` dict (same object that was passed in).
        """
        # Ensure routing_decisions list exists
        if "routing_decisions" not in metadata:
            metadata["routing_decisions"] = []

        metadata["routing_decisions"].append(
            {
                "dimension": finding.dimension.value,
                "summary": finding.summary,
                "new_routing": decision.value,
            }
        )

        # Scope Modification accepted — permanently tag the node as mutated
        if decision == MitigationRoutingEnum.SCOPE_MODIFICATION:
            if "tags" not in metadata:
                metadata["tags"] = []
            if _MUTATED_TAG not in metadata["tags"]:
                metadata["tags"].append(_MUTATED_TAG)

        return metadata
