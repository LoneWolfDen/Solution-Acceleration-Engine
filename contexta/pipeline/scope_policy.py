"""Unalterable Scope Policy enforcer.

Detects ``IssueFinding`` objects with ``mitigation_routing = SCOPE_MODIFICATION``
across all dimension payloads and manages the routing decision recording in
``metadata_json``.

Design contracts
----------------
- ``get_scope_findings()`` filters across all payloads and findings (Property 17).
- ``apply_routing_decision()`` appends to ``metadata["routing_decisions"]`` and
  returns the updated dict — it does not mutate the finding in-place.
"""

from __future__ import annotations

from typing import List

from ..models.enums import MitigationRoutingEnum
from ..models.findings import IssueFinding
from ..models.payloads import ReviewNodePayload


class ScopePolicyEnforcer:
    """Detects scope-modification findings and records routing decisions."""

    def get_scope_findings(
        self,
        payloads: List[ReviewNodePayload],
    ) -> List[IssueFinding]:
        """Return all findings with ``mitigation_routing == SCOPE_MODIFICATION``.

        Parameters
        ----------
        payloads:
            All dimension payloads from the current Layer 1 run.

        Returns
        -------
        List[IssueFinding]
            Every finding across all payloads whose routing is
            ``SCOPE_MODIFICATION``.
        """
        findings: List[IssueFinding] = []
        for payload in payloads:
            for finding in payload.findings:
                if finding.mitigation_routing == MitigationRoutingEnum.SCOPE_MODIFICATION:
                    findings.append(finding)
        return findings

    def apply_routing_decision(
        self,
        finding: IssueFinding,
        decision: MitigationRoutingEnum,
        metadata: dict,
    ) -> dict:
        """Record a routing decision in *metadata* and return the updated dict.

        Parameters
        ----------
        finding:
            The ``IssueFinding`` whose routing is being changed.
        decision:
            The new ``MitigationRoutingEnum`` value chosen by the user.
        metadata:
            The current node ``metadata_json`` dict.

        Returns
        -------
        dict
            Updated metadata dict with the new entry appended to
            ``metadata["routing_decisions"]``.
        """
        decisions: list = metadata.get("routing_decisions", [])
        decisions.append(
            {
                "dimension": finding.dimension.value,
                "summary": finding.summary,
                "new_routing": decision.value,
            }
        )
        metadata["routing_decisions"] = decisions
        return metadata
