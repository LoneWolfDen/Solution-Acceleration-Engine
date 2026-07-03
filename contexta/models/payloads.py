"""ReviewNodePayload Pydantic model.

The validated output of a single dimension review.  Every LLM response MUST
pass through ``ReviewNodePayload.model_validate_json()`` before any downstream
processing or database write occurs.

``raw_llm_response`` is a transport-layer annotation set by the dimension runner
*after* the LLM response is received.  It is never sent to the LLM as part of
the output schema — use ``llm_schema_json()`` to obtain the schema string safe
for prompt injection.
"""

import copy
import json
from typing import List

from pydantic import BaseModel

from .enums import ConfidenceEnum, ReviewDimensionEnum
from .findings import IssueFinding

# Field excluded from the schema shown to the LLM — it is injected by the
# runner after parsing and must never be produced by the model itself.
_LLM_EXCLUDED_FIELDS = {"raw_llm_response"}


class ReviewNodePayload(BaseModel):
    dimension: ReviewDimensionEnum
    findings: List[IssueFinding]
    overall_confidence: ConfidenceEnum
    raw_llm_response: str

    @classmethod
    def llm_schema_json(cls) -> str:
        """Return the JSON Schema string for use in LLM prompts.

        Strips ``raw_llm_response`` from the schema so the LLM is never asked
        to produce a field that the runner injects post-parse.
        """
        schema = copy.deepcopy(cls.model_json_schema())
        for field in _LLM_EXCLUDED_FIELDS:
            schema.get("properties", {}).pop(field, None)
            if "required" in schema:
                schema["required"] = [f for f in schema["required"] if f != field]
        return json.dumps(schema, indent=2)
