"""Property 11 — Active Blueprint Prompt Inclusion.

For any active ``PromptBlueprint`` record with ``master_prompt_text = T`` and
any ``ReviewDimensionEnum`` value ``D``, the system prompt produced by
``PromptBuilder.build_dimension_prompt(D, ...)`` must contain ``T`` as a
substring.

This guarantees that swapping the active blueprint in the Admin Tab is
immediately reflected in every dimension review prompt — no stale prompt
caching, no partial substitution.

This module covers:
1. Unit tests with all 12 dimension values and varied blueprint texts.
2. A Hypothesis property test with arbitrary ``master_prompt_text`` strings
   and all 12 dimension enum values.
3. Additional structural assertions: CRITICAL OUTPUT INSTRUCTIONS block
   presence, arbitrator prompt JSON directive presence.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from contexta.db.models import BlueprintRow
from contexta.llm.prompts import (
    ARBITRATOR_SYSTEM_TEMPLATE,
    DIMENSION_SYSTEM_TEMPLATE,
    PromptBuilder,
)
from contexta.models.enums import ReviewDimensionEnum


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_builder(master_prompt_text: str) -> PromptBuilder:
    blueprint = BlueprintRow(
        id="bp-test",
        blueprint_name="Test Blueprint",
        version_string="1.0.0",
        master_prompt_text=master_prompt_text,
        is_active=True,
    )
    return PromptBuilder(blueprint=blueprint)


# ── Template structure tests ──────────────────────────────────────────────────


class TestDimensionSystemTemplate:
    """The DIMENSION_SYSTEM_TEMPLATE must have the required placeholder slots."""

    def test_has_dimension_placeholder(self):
        assert "{dimension}" in DIMENSION_SYSTEM_TEMPLATE

    def test_has_master_prompt_text_placeholder(self):
        assert "{master_prompt_text}" in DIMENSION_SYSTEM_TEMPLATE

    def test_has_concrete_example_in_template(self):
        assert "FIELD RULES" in DIMENSION_SYSTEM_TEMPLATE

    def test_critical_output_instructions_present(self):
        assert "CRITICAL OUTPUT INSTRUCTIONS" in DIMENSION_SYSTEM_TEMPLATE

    def test_no_markdown_fence_instruction(self):
        assert "markdown code fences" in DIMENSION_SYSTEM_TEMPLATE.lower() or \
               "```" in DIMENSION_SYSTEM_TEMPLATE or \
               "code fences" in DIMENSION_SYSTEM_TEMPLATE.lower()

    def test_raw_json_instruction_present(self):
        assert "raw JSON" in DIMENSION_SYSTEM_TEMPLATE or \
               "raw json" in DIMENSION_SYSTEM_TEMPLATE.lower()


class TestArbitratorSystemTemplate:
    """The ARBITRATOR_SYSTEM_TEMPLATE must mirror the JSON output directive."""

    def test_critical_output_instructions_present(self):
        assert "CRITICAL OUTPUT INSTRUCTIONS" in ARBITRATOR_SYSTEM_TEMPLATE

    def test_raw_json_instruction_present(self):
        template_lower = ARBITRATOR_SYSTEM_TEMPLATE.lower()
        assert "raw json" in template_lower or "raw JSON" in ARBITRATOR_SYSTEM_TEMPLATE

    def test_contradictions_key_mentioned(self):
        assert "contradictions" in ARBITRATOR_SYSTEM_TEMPLATE


# ── Blueprint inclusion unit tests ────────────────────────────────────────────


class TestBlueprintInclusionInDimensionPrompt:
    """``build_dimension_prompt()`` must embed master_prompt_text verbatim."""

    @pytest.mark.parametrize("dimension", list(ReviewDimensionEnum))
    def test_master_prompt_text_in_system_for_all_dimensions(
        self,
        dimension: ReviewDimensionEnum,
        blueprint_row: BlueprintRow,
    ):
        """All 12 dimensions must include master_prompt_text in system prompt."""
        builder = PromptBuilder(blueprint=blueprint_row)
        system, _ = builder.build_dimension_prompt(dimension, artifact_context="artifacts")
        assert blueprint_row.master_prompt_text in system, (
            f"master_prompt_text not found in system prompt for dimension {dimension.value}"
        )

    def test_dimension_value_in_system_prompt(
        self,
        blueprint_row: BlueprintRow,
    ):
        """Dimension name appears in the system prompt."""
        builder = PromptBuilder(blueprint=blueprint_row)
        system, _ = builder.build_dimension_prompt(
            ReviewDimensionEnum.ARCHITECTURE, artifact_context="ctx"
        )
        assert "Architecture" in system

    def test_dimension_value_in_concrete_example(
        self,
        blueprint_row: BlueprintRow,
    ):
        """Dimension name appears inside the concrete example in the system prompt."""
        builder = PromptBuilder(blueprint=blueprint_row)
        system, _ = builder.build_dimension_prompt(
            ReviewDimensionEnum.RISK, artifact_context=""
        )
        assert "Risk" in system

    def test_critical_instructions_in_system_prompt(
        self,
        blueprint_row: BlueprintRow,
    ):
        """CRITICAL OUTPUT INSTRUCTIONS block is always present."""
        builder = PromptBuilder(blueprint=blueprint_row)
        system, _ = builder.build_dimension_prompt(
            ReviewDimensionEnum.SCOPE, artifact_context=""
        )
        assert "CRITICAL OUTPUT INSTRUCTIONS" in system

    def test_user_prompt_contains_artifact_context(
        self,
        blueprint_row: BlueprintRow,
    ):
        """Artifact context appears in the user prompt, not the system prompt."""
        artifact_ctx = "FILE: /docs/proposal.md (100 lines)\nContent here"
        builder = PromptBuilder(blueprint=blueprint_row)
        _, user = builder.build_dimension_prompt(
            ReviewDimensionEnum.INTENT, artifact_context=artifact_ctx
        )
        assert artifact_ctx in user
        assert "PROPOSAL ARTIFACTS" in user

    def test_different_blueprints_produce_different_system_prompts(self):
        """Two blueprints with different texts produce different system prompts."""
        builder_a = _make_builder("Focus on delivery timeline risk only.")
        builder_b = _make_builder("Focus on commercial viability exclusively.")
        sys_a, _ = builder_a.build_dimension_prompt(
            ReviewDimensionEnum.TIMELINE, artifact_context=""
        )
        sys_b, _ = builder_b.build_dimension_prompt(
            ReviewDimensionEnum.TIMELINE, artifact_context=""
        )
        assert sys_a != sys_b

    def test_empty_artifact_context_produces_valid_user_prompt(
        self,
        blueprint_row: BlueprintRow,
    ):
        """Empty artifact context still produces a parseable user prompt."""
        builder = PromptBuilder(blueprint=blueprint_row)
        _, user = builder.build_dimension_prompt(
            ReviewDimensionEnum.NFR, artifact_context=""
        )
        assert "PROPOSAL ARTIFACTS" in user

    def test_multiline_master_prompt_text_preserved(self):
        """Multiline master_prompt_text is embedded exactly, newlines intact."""
        multiline = "Line one.\nLine two.\nLine three with special chars: <>\"'"
        builder = _make_builder(multiline)
        system, _ = builder.build_dimension_prompt(
            ReviewDimensionEnum.OWNERSHIP, artifact_context=""
        )
        assert multiline in system
# ── Arbitrator prompt tests ───────────────────────────────────────────────────


class TestArbitratorPrompt:
    """``build_arbitrator_prompt()`` structural assertions."""

    def test_system_contains_critical_instructions(
        self,
        blueprint_row: BlueprintRow,
    ):
        builder = PromptBuilder(blueprint=blueprint_row)
        system, _ = builder.build_arbitrator_prompt(payloads=[])
        assert "CRITICAL OUTPUT INSTRUCTIONS" in system

    def test_user_contains_all_payloads(
        self,
        blueprint_row: BlueprintRow,
    ):
        payloads = [f'{{"payload": {i}}}' for i in range(12)]
        builder = PromptBuilder(blueprint=blueprint_row)
        _, user = builder.build_arbitrator_prompt(payloads=payloads)
        for p in payloads:
            assert p in user

    def test_user_payload_numbering(
        self,
        blueprint_row: BlueprintRow,
    ):
        """Each payload is labelled with a 1-based index separator."""
        payloads = ['{"a": 1}', '{"b": 2}', '{"c": 3}']
        builder = PromptBuilder(blueprint=blueprint_row)
        _, user = builder.build_arbitrator_prompt(payloads=payloads)
        assert "--- 1 ---" in user
        assert "--- 2 ---" in user
        assert "--- 3 ---" in user

    def test_empty_payloads_produces_valid_prompts(
        self,
        blueprint_row: BlueprintRow,
    ):
        builder = PromptBuilder(blueprint=blueprint_row)
        system, user = builder.build_arbitrator_prompt(payloads=[])
        assert isinstance(system, str) and len(system) > 0
        assert isinstance(user, str)

    def test_return_type_is_tuple_of_two_strings(
        self,
        blueprint_row: BlueprintRow,
    ):
        builder = PromptBuilder(blueprint=blueprint_row)
        result = builder.build_dimension_prompt(ReviewDimensionEnum.RISK, "ctx")
        assert isinstance(result, tuple) and len(result) == 2
        assert all(isinstance(s, str) for s in result)


# ── Hypothesis property test ──────────────────────────────────────────────────


@given(
    master_prompt_text=st.text(min_size=1, max_size=2000),
    dimension=st.sampled_from(list(ReviewDimensionEnum)),
    artifact_context=st.text(max_size=500),
)
@settings(max_examples=500)
def test_property_11_blueprint_text_always_in_system_prompt(
    master_prompt_text: str,
    dimension: ReviewDimensionEnum,
    artifact_context: str,
) -> None:
    """Property 11: master_prompt_text T is a substring of build_dimension_prompt() system.

    For ANY master_prompt_text T, ANY ReviewDimensionEnum value D, and ANY
    artifact_context, the system string returned by build_dimension_prompt(D, ...)
    MUST contain T as a verbatim substring.
    """
    builder = _make_builder(master_prompt_text)
    system, _ = builder.build_dimension_prompt(dimension, artifact_context)

    assert master_prompt_text in system, (
        f"master_prompt_text not found in system prompt.\n"
        f"dimension={dimension.value!r}\n"
        f"master_prompt_text={master_prompt_text!r}\n"
        f"system_prompt (first 200 chars)={system[:200]!r}"
    )
