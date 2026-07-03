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
- The JSON object MUST conform exactly to this example structure:

{{
  "dimension": "{dimension}",
  "findings": [
    {{
      "dimension": "{dimension}",
      "confidence": "AMBER",
      "summary": "One-sentence summary of the issue.",
      "detail": "Full explanation of the issue and its impact.",
      "citations": [
        {{
          "file_path": "path/to/artifact.md",
          "line_start": 1,
          "line_end": 5,
          "citation_type": "Direct Reference",
          "excerpt": "Verbatim or paraphrased text from the source."
        }}
      ],
      "mitigation_routing": "Risk Register"
    }}
  ],
  "overall_confidence": "AMBER"
}}

FIELD RULES:
- "dimension" must be exactly: {dimension}
- "confidence" and "overall_confidence" must be one of: RED, AMBER, GREEN
- "citation_type" must be one of: "Direct Reference", "Advised in Relation"
- "mitigation_routing" must be one of: "Scope Modification", "Risk Register", "Assumptions Matrix", "Both R&A", "Ignored"
- "findings" may be an empty list [] if no issues are found
- "line_start" and "line_end" must be integers >= 1
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
    """

    def __init__(self, blueprint: BlueprintRow) -> None:
        self._blueprint = blueprint

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
        - A concrete example of the expected ``ReviewNodePayload`` structure

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



# ── Layer 2 Synthesis prompt ──────────────────────────────────────────────────

LAYER2_SYNTHESIS_SYSTEM_TEMPLATE = """\
You are the Layer 2 Synthesis Arbitrator. Analyse the collected findings from \
all 12 project dimension reviews and produce a single authoritative \
ReconciliationReport.

Your responsibilities:
1. Identify cross-dimension conflicts where findings contradict or undermine \
each other. Cite specific source references for every conflict identified.
2. Assess overall delivery confidence as a score from 1 (certain to fail) \
to 100 (certain to succeed).
3. Enumerate architectural and technical risks that could derail delivery.
4. Write a candid executive summary of overall project viability.
5. List sequential, actionable recommendations to unblock or improve the proposal.
6. Set ready_for_approval to true only if the proposal is structurally sound.

CRITICAL OUTPUT INSTRUCTIONS:
- Respond with a single, raw JSON object only.
- Do NOT use markdown code fences, preamble, or commentary.
- Your entire response must be valid JSON starting with {{ and ending with }}.
- The JSON object must conform exactly to this schema:
{schema_json}
"""

# Inline schema description embedded in the system prompt so the model sees
# the exact field names and types it must produce.  Single braces are correct
# here: this string is a substituted *value*, not a format template — Python's
# str.format() does not re-process substitution values.
_RECONCILIATION_SCHEMA_INLINE = """\
{
  "executive_summary": "<string — candid synthesis of project viability>",
  "delivery_confidence_score": <integer 1-100>,
  "critical_conflicts": [
    {
      "dimensions_involved": ["<DimensionA>", "<DimensionB>"],
      "description": "<why these dimensions conflict>",
      "severity": "<Low | Medium | High | Critical>",
      "source_references": ["<e.g. SOW Section 3>"],
      "suggested_mitigation": "<practical resolution steps>"
    }
  ],
  "architectural_risks": ["<risk description>"],
  "actionable_recommendations": ["<sequential step>"],
  "ready_for_approval": <true | false>
}"""


def build_synthesis_prompt(findings: list) -> tuple[str, str]:
    """Return ``(system_prompt, user_prompt)`` for the Layer 2 synthesis call.

    Formats all ``IssueFinding`` objects into a numbered context block so the
    model has grounded, citable source material to reason against.

    Parameters
    ----------
    findings:
        List of ``IssueFinding`` objects aggregated across all 12 dimensions.
        An empty list is accepted — the model will produce a minimal report.

    Returns
    -------
    tuple[str, str]
        ``(system_prompt, user_prompt)``
    """
    system = LAYER2_SYNTHESIS_SYSTEM_TEMPLATE.format(
        schema_json=_RECONCILIATION_SCHEMA_INLINE
    )

    if not findings:
        user = (
            "No findings were produced by Layer 1. "
            "Produce a minimal ReconciliationReport reflecting no identified issues."
        )
        return system, user

    lines: list[str] = []
    for i, f in enumerate(findings, start=1):
        if f.citations:
            citation_str = "; ".join(
                f"{c.file_path}:{c.line_start}-{c.line_end} ({c.excerpt!r})"
                for c in f.citations
            )
        else:
            citation_str = "no citations"

        lines.append(
            f"[{i}] Dimension={f.dimension.value} | Confidence={f.confidence.value} "
            f"| Routing={f.mitigation_routing.value}\n"
            f"    Summary: {f.summary}\n"
            f"    Detail:  {f.detail}\n"
            f"    Citations: {citation_str}"
        )

    user = "LAYER 1 FINDINGS:\n\n" + "\n\n".join(lines)
    return system, user
