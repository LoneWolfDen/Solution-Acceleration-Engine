"""Prompt builder for dimension reviews and Layer 2 Arbitrator synthesis.

Design contracts
----------------
1. **Raw JSON output enforcement** — ``DIMENSION_SYSTEM_TEMPLATE`` contains a
   CRITICAL OUTPUT INSTRUCTIONS block that explicitly commands the model to
   return a single, unwrapped JSON object with no markdown code fences,
   preamble, or commentary.  This is a defence-in-depth safeguard for local
   Ollama deployments that do not universally honour the ``json_object``
   ``response_format`` flag across all model families.

2. **Blueprint inclusion** — ``build_dimension_prompt()`` embeds the active
   blueprint's ``master_prompt_text`` verbatim inside the system string.
   Property 11 (Active Blueprint Prompt Inclusion) asserts that for *any*
   ``master_prompt_text`` value ``T`` and any ``ReviewDimensionEnum`` value
   ``D``, the returned system string contains ``T`` as a substring.

3. **Arbitrator parity** — ``build_arbitrator_prompt()`` carries the same
   CRITICAL OUTPUT INSTRUCTIONS block to guarantee consistent parsing
   behaviour across both pipeline layers.
"""

from __future__ import annotations

from ..db.models import BlueprintRow
from ..models.enums import ReviewDimensionEnum

# ── System prompt template ────────────────────────────────────────────────────

DIMENSION_SYSTEM_TEMPLATE = """\
You are a solution review AI operating as the {dimension} reviewer.

{master_prompt_text}

CRITICAL OUTPUT INSTRUCTIONS:
- You MUST respond with a single, raw JSON object.
- Do NOT wrap your response in markdown code fences (no ```json or ``` blocks).
- Do NOT include any explanatory text, preamble, or commentary before or after the JSON.
- Do NOT use any formatting other than the JSON structure itself.
- Your entire response must be valid, parseable JSON starting with {{ and ending with }}.
- The JSON object MUST conform exactly to this schema:
{schema_json}
"""

ARBITRATOR_SYSTEM_TEMPLATE = """\
You are the Arbitrator Persona. Analyse the 12 dimension review outputs \
and identify all contradictions.

CRITICAL OUTPUT INSTRUCTIONS:
- Respond with a single, raw JSON object only.
- Do NOT use markdown code fences, preamble, or commentary.
- Your entire response must be valid JSON starting with {{ and ending with }}.
- The JSON object must have a single key "contradictions" containing a list \
of objects, each with keys: "dimension_a", "dimension_b", "description".
"""


# ── PromptBuilder ─────────────────────────────────────────────────────────────


class PromptBuilder:
    """Assembles (system, user) prompt pairs for dimension reviews and arbitration.

    Parameters
    ----------
    blueprint:
        The active ``BlueprintRow`` fetched from ``prompt_blueprints``.
        ``master_prompt_text`` is embedded verbatim in every dimension prompt.
    schema_json:
        JSON Schema string describing the expected ``ReviewNodePayload`` shape.
        Embedded in the dimension system prompt so the model sees the exact
        contract it must satisfy.
    """

    def __init__(self, blueprint: BlueprintRow, schema_json: str) -> None:
        self._blueprint = blueprint
        self._schema_json = schema_json

    # ── Public methods ────────────────────────────────────────────────────────

    def build_dimension_prompt(
        self,
        dimension: ReviewDimensionEnum,
        artifact_context: str,
    ) -> tuple[str, str]:
        """Return ``(system_prompt, user_prompt)`` for a single dimension review.

        The system prompt unconditionally contains:
        - The dimension name
        - The full ``master_prompt_text`` from the active blueprint
        - The CRITICAL OUTPUT INSTRUCTIONS block (raw JSON, no fences)
        - The ``ReviewNodePayload`` JSON schema

        The user prompt contains all ingested artifact content formatted as a
        labelled block so the model has grounded, citable source material.

        Parameters
        ----------
        dimension:
            The ``ReviewDimensionEnum`` value identifying which axis to review.
        artifact_context:
            Concatenated artifact content produced by
            ``ArtifactRegistry.build_context_string()``.

        Returns
        -------
        tuple[str, str]
            ``(system_prompt, user_prompt)``
        """
        system = DIMENSION_SYSTEM_TEMPLATE.format(
            dimension=dimension.value,
            master_prompt_text=self._blueprint.master_prompt_text,
            schema_json=self._schema_json,
        )
        user = f"PROPOSAL ARTIFACTS:\n\n{artifact_context}"
        return system, user

    def build_arbitrator_prompt(
        self,
        payloads: list[str],
    ) -> tuple[str, str]:
        """Return ``(system_prompt, user_prompt)`` for the Layer 2 Arbitrator.

        The system prompt carries the same CRITICAL OUTPUT INSTRUCTIONS block
        as dimension prompts, enforcing raw JSON output for parsing stability.

        Parameters
        ----------
        payloads:
            List of ``ReviewNodePayload.model_dump_json()`` strings — one per
            completed dimension review (exactly 12 expected by the Arbitrator).

        Returns
        -------
        tuple[str, str]
            ``(system_prompt, user_prompt)``
        """
        system = ARBITRATOR_SYSTEM_TEMPLATE
        user = "\n\n".join(f"--- {i + 1} ---\n{p}" for i, p in enumerate(payloads))
        return system, user
