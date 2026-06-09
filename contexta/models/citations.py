"""SourceCitation Pydantic model.

Represents a reference to a specific file and line range produced during a
dimension review.  The ``line_end >= line_start`` invariant is enforced via a
Pydantic field validator so that malformed LLM output is caught at the schema
boundary before it can propagate downstream.
"""

from pydantic import BaseModel, field_validator, model_validator

from .enums import CitationTypeEnum


class SourceCitation(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    citation_type: CitationTypeEnum
    excerpt: str

    @model_validator(mode="after")
    def _end_gte_start(self) -> "SourceCitation":
        if self.line_end < self.line_start:
            raise ValueError(
                f"line_end ({self.line_end}) must be >= line_start ({self.line_start})"
            )
        return self
