"""Property 17 — Scope Policy Routing Decision Persistence.

For any ``IssueFinding`` with ``SCOPE_MODIFICATION`` routing and any valid
``MitigationRoutingEnum`` decision, ``ScopePolicyEnforcer.apply_routing_decision()``
must:
1. Return a metadata dict containing a ``routing_decisions`` entry whose
   ``new_routing`` equals ``decision.value``.
2. Include the ``"dimension"`` and ``"summary"`` fields from the finding.
3. When ``decision == SCOPE_MODIFICATION``, append ``"#MUTATED"`` to
   ``metadata["tags"]`` (creating the list if absent, never duplicating).
4. Never overwrite existing ``routing_decisions`` entries.
5. Return the same dict object that was passed in (in-place mutation).

Coverage
--------
- Unit: routing_decisions entry created for each routing enum value.
- Unit: #MUTATED tag appended only for SCOPE_MODIFICATION decision.
- Unit: #MUTATED not added for other decisions.
- Unit: pre-existing routing_decisions are preserved.
- Unit: pre-existing tags preserved; #MUTATED not duplicated.
- Unit: get_scope_findings correctly filters SCOPE_MODIFICATION.
- Unit: get_scope_findings returns empty for non-SCOPE_MODIFICATION findings.
- Hypothesis: Property 17 — new_routing always equals decision.value.
"""

from __future__ import annotations

import asyncio
from typing import List
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contexta.models.citations import SourceCitation
from contexta.models.enums import (
    CitationTypeEnum,
    ConfidenceEnum,
    MitigationRoutingEnum,
    ReviewDimensionEnum,
)
from contexta.models.findings import IssueFinding
from contexta.models.payloads import ReviewNodePayload
from contexta.pipeline.scope_policy import ScopePolicyEnforcer, _MUTATED_TAG


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_finding(
    routing: MitigationRoutingEnum = MitigationRoutingEnum.SCOPE_MODIFICATION,
    dimension: ReviewDimensionEnum = ReviewDimensionEnum.SCOPE,
    summary: str = "Scope change required",
) -> IssueFinding:
    return IssueFinding(
        dimension=dimension,
        confidence=ConfidenceEnum.AMBER,
        summary=summary,
        detail="Detailed explanation of scope change.",
        citations=[],
        mitigation_routing=routing,
    )


def _make_payload_with_findings(findings: List[IssueFinding]) -> ReviewNodePayload:
    return ReviewNodePayload(
        dimension=findings[0].dimension if findings else ReviewDimensionEnum.SCOPE,
        findings=findings,
        overall_confidence=ConfidenceEnum.AMBER,
        raw_llm_response='{"ok": true}',
    )


# ── ScopePolicyEnforcer.apply_routing_decision ───────────────────────────────


class TestApplyRoutingDecision:

    def test_routing_decision_stored_in_metadata(self):
        """A new routing_decisions entry is appended to metadata."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding()
        metadata = {}
        enforcer.apply_routing_decision(finding, MitigationRoutingEnum.RISK_REGISTER, metadata)
        assert "routing_decisions" in metadata
        assert len(metadata["routing_decisions"]) == 1

    @pytest.mark.parametrize("decision", list(MitigationRoutingEnum))
    def test_new_routing_equals_decision_value(self, decision: MitigationRoutingEnum):
        """routing_decisions[0].new_routing == decision.value for all enum members."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding()
        metadata = {}
        enforcer.apply_routing_decision(finding, decision, metadata)
        assert metadata["routing_decisions"][0]["new_routing"] == decision.value

    def test_dimension_stored_in_routing_entry(self):
        """The finding's dimension.value is stored in the routing entry."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding(dimension=ReviewDimensionEnum.RISK)
        metadata = {}
        enforcer.apply_routing_decision(finding, MitigationRoutingEnum.RISK_REGISTER, metadata)
        assert metadata["routing_decisions"][0]["dimension"] == "Risk"

    def test_summary_stored_in_routing_entry(self):
        """The finding's summary is stored in the routing entry."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding(summary="Critical scope gap identified")
        metadata = {}
        enforcer.apply_routing_decision(finding, MitigationRoutingEnum.ASSUMPTIONS_MATRIX, metadata)
        assert metadata["routing_decisions"][0]["summary"] == "Critical scope gap identified"

    def test_scope_modification_adds_mutated_tag(self):
        """Decision == SCOPE_MODIFICATION appends #MUTATED to metadata['tags']."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding()
        metadata = {}
        enforcer.apply_routing_decision(
            finding, MitigationRoutingEnum.SCOPE_MODIFICATION, metadata
        )
        assert "tags" in metadata
        assert _MUTATED_TAG in metadata["tags"]

    def test_risk_register_does_not_add_mutated_tag(self):
        """RISK_REGISTER decision must not add #MUTATED tag."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding()
        metadata = {}
        enforcer.apply_routing_decision(
            finding, MitigationRoutingEnum.RISK_REGISTER, metadata
        )
        assert _MUTATED_TAG not in metadata.get("tags", [])

    def test_assumptions_matrix_does_not_add_mutated_tag(self):
        """ASSUMPTIONS_MATRIX decision must not add #MUTATED tag."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding()
        metadata = {}
        enforcer.apply_routing_decision(
            finding, MitigationRoutingEnum.ASSUMPTIONS_MATRIX, metadata
        )
        assert _MUTATED_TAG not in metadata.get("tags", [])

    def test_ignored_does_not_add_mutated_tag(self):
        """IGNORED decision must not add #MUTATED tag."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding()
        metadata = {}
        enforcer.apply_routing_decision(
            finding, MitigationRoutingEnum.IGNORED, metadata
        )
        assert _MUTATED_TAG not in metadata.get("tags", [])

    def test_mutated_tag_not_duplicated_on_repeated_scope_modification(self):
        """Calling apply_routing_decision twice with SCOPE_MODIFICATION adds #MUTATED once."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding()
        metadata = {}
        enforcer.apply_routing_decision(
            finding, MitigationRoutingEnum.SCOPE_MODIFICATION, metadata
        )
        enforcer.apply_routing_decision(
            finding, MitigationRoutingEnum.SCOPE_MODIFICATION, metadata
        )
        assert metadata["tags"].count(_MUTATED_TAG) == 1

    def test_existing_routing_decisions_preserved(self):
        """Pre-existing routing_decisions entries are not overwritten."""
        enforcer = ScopePolicyEnforcer()
        metadata = {
            "routing_decisions": [
                {"dimension": "Risk", "summary": "old entry", "new_routing": "Risk Register"}
            ]
        }
        finding = _make_finding(dimension=ReviewDimensionEnum.SCOPE, summary="new scope entry")
        enforcer.apply_routing_decision(
            finding, MitigationRoutingEnum.ASSUMPTIONS_MATRIX, metadata
        )
        assert len(metadata["routing_decisions"]) == 2
        assert metadata["routing_decisions"][0]["summary"] == "old entry"
        assert metadata["routing_decisions"][1]["summary"] == "new scope entry"

    def test_existing_tags_preserved_when_mutated_appended(self):
        """Pre-existing tags are kept when #MUTATED is added."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding()
        metadata = {"tags": ["#FinServ", "#LeanTeam"]}
        enforcer.apply_routing_decision(
            finding, MitigationRoutingEnum.SCOPE_MODIFICATION, metadata
        )
        assert "#FinServ" in metadata["tags"]
        assert "#LeanTeam" in metadata["tags"]
        assert _MUTATED_TAG in metadata["tags"]

    def test_returns_same_metadata_object(self):
        """apply_routing_decision returns the same dict that was passed in."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding()
        metadata = {}
        result = enforcer.apply_routing_decision(
            finding, MitigationRoutingEnum.RISK_REGISTER, metadata
        )
        assert result is metadata

    def test_routing_decisions_key_created_if_absent(self):
        """routing_decisions list is initialised if the key was absent."""
        enforcer = ScopePolicyEnforcer()
        finding = _make_finding()
        metadata = {"some_other_key": "value"}
        enforcer.apply_routing_decision(finding, MitigationRoutingEnum.IGNORED, metadata)
        assert isinstance(metadata["routing_decisions"], list)
        assert len(metadata["routing_decisions"]) == 1

    def test_multiple_decisions_accumulate(self):
        """Calling apply_routing_decision multiple times appends, never replaces."""
        enforcer = ScopePolicyEnforcer()
        metadata = {}
        for decision in [
            MitigationRoutingEnum.RISK_REGISTER,
            MitigationRoutingEnum.ASSUMPTIONS_MATRIX,
            MitigationRoutingEnum.IGNORED,
        ]:
            finding = _make_finding(summary=f"finding for {decision.value}")
            enforcer.apply_routing_decision(finding, decision, metadata)

        assert len(metadata["routing_decisions"]) == 3


# ── ScopePolicyEnforcer.get_scope_findings ────────────────────────────────────


class TestGetScopeFindings:

    def test_filters_scope_modification_findings(self):
        """Only SCOPE_MODIFICATION findings are returned."""
        scope_finding = _make_finding(routing=MitigationRoutingEnum.SCOPE_MODIFICATION)
        risk_finding = _make_finding(routing=MitigationRoutingEnum.RISK_REGISTER)
        payload = _make_payload_with_findings([scope_finding, risk_finding])

        enforcer = ScopePolicyEnforcer()
        results = enforcer.get_scope_findings([payload])
        assert len(results) == 1
        assert results[0].mitigation_routing == MitigationRoutingEnum.SCOPE_MODIFICATION

    def test_no_scope_findings_returns_empty_list(self):
        """Empty list returned when no SCOPE_MODIFICATION findings exist."""
        finding = _make_finding(routing=MitigationRoutingEnum.IGNORED)
        payload = _make_payload_with_findings([finding])
        enforcer = ScopePolicyEnforcer()
        assert enforcer.get_scope_findings([payload]) == []

    def test_empty_payloads_returns_empty_list(self):
        """Empty payload list → empty findings list."""
        enforcer = ScopePolicyEnforcer()
        assert enforcer.get_scope_findings([]) == []

    def test_multiple_payloads_scope_findings_aggregated(self):
        """Scope findings across multiple payloads are all returned."""
        p1 = _make_payload_with_findings([
            _make_finding(routing=MitigationRoutingEnum.SCOPE_MODIFICATION, dimension=ReviewDimensionEnum.SCOPE),
        ])
        p2 = _make_payload_with_findings([
            _make_finding(routing=MitigationRoutingEnum.SCOPE_MODIFICATION, dimension=ReviewDimensionEnum.INTENT),
        ])
        p3 = _make_payload_with_findings([
            _make_finding(routing=MitigationRoutingEnum.RISK_REGISTER, dimension=ReviewDimensionEnum.RISK),
        ])
        enforcer = ScopePolicyEnforcer()
        results = enforcer.get_scope_findings([p1, p2, p3])
        assert len(results) == 2

    def test_original_payloads_not_mutated(self):
        """get_scope_findings does not mutate the input list."""
        finding = _make_finding(routing=MitigationRoutingEnum.SCOPE_MODIFICATION)
        payload = _make_payload_with_findings([finding])
        original_len = len(payload.findings)
        enforcer = ScopePolicyEnforcer()
        enforcer.get_scope_findings([payload])
        assert len(payload.findings) == original_len


# ── Hypothesis: Property 17 ───────────────────────────────────────────────────


@given(
    decision=st.sampled_from(list(MitigationRoutingEnum)),
    dimension=st.sampled_from(list(ReviewDimensionEnum)),
    summary=st.text(min_size=1, max_size=200),
    existing_decisions=st.lists(
        st.fixed_dictionaries({
            "dimension": st.sampled_from([d.value for d in ReviewDimensionEnum]),
            "summary": st.text(min_size=1, max_size=50),
            "new_routing": st.sampled_from([r.value for r in MitigationRoutingEnum]),
        }),
        max_size=5,
    ),
)
@settings(max_examples=300)
def test_property_17_routing_decision_persistence(
    decision: MitigationRoutingEnum,
    dimension: ReviewDimensionEnum,
    summary: str,
    existing_decisions: list,
) -> None:
    """Property 17: new_routing == decision.value for any finding and decision.

    Also asserts:
    - routing_decisions list grows by exactly 1.
    - #MUTATED added iff decision == SCOPE_MODIFICATION.
    - Pre-existing routing_decisions entries are preserved.
    """
    enforcer = ScopePolicyEnforcer()
    finding = _make_finding(
        routing=MitigationRoutingEnum.SCOPE_MODIFICATION,
        dimension=dimension,
        summary=summary,
    )
    metadata: dict = {"routing_decisions": list(existing_decisions)}
    prior_count = len(existing_decisions)

    result = enforcer.apply_routing_decision(finding, decision, metadata)

    # new_routing must exactly equal decision.value
    assert result["routing_decisions"][-1]["new_routing"] == decision.value, (
        f"new_routing={result['routing_decisions'][-1]['new_routing']!r} "
        f"!= {decision.value!r}"
    )

    # list grew by exactly 1
    assert len(result["routing_decisions"]) == prior_count + 1, (
        f"Expected {prior_count + 1} entries, got {len(result['routing_decisions'])}"
    )

    # #MUTATED tag logic
    if decision == MitigationRoutingEnum.SCOPE_MODIFICATION:
        assert _MUTATED_TAG in result.get("tags", []), (
            f"#MUTATED not found in tags for SCOPE_MODIFICATION decision"
        )
    else:
        assert _MUTATED_TAG not in result.get("tags", []), (
            f"#MUTATED unexpectedly present for decision {decision.value!r}"
        )

    # pre-existing entries preserved
    for i, entry in enumerate(existing_decisions):
        assert result["routing_decisions"][i] == entry, (
            f"Existing entry at index {i} was mutated"
        )
