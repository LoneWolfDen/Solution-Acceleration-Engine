"""
contexta/models/citations.py — SourceCitation Pydantic model.

Every reference to a source file produced during a dimension review is wrapped
in a SourceCitation.  The line range is validated to be non-inverted so that
TUI scroll targets are always deterministic.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator, model_validator

from .enums import CitationTypeEnum


class SourceCitation(BaseModel):
    """
    A reference to a specific span of lines within an ingested source file.

    Attributes:
        file_path:     Path of the ingested file as recorded by ArtifactRegistry.
        line_start:    1-based start of the referenced range (inclusive).
        line_end:      1-based end of the referenced range (inclusive).
        citation_type: Whether this is a direct reference or advised relation.
        excerpt:       Short verbatim or paraphrased text from the cited span.
    """

    file_path:     str
    line_start:    int
    line_end:      int
    citation_type: CitationTypeEnum
    excerpt:       str

    @field_validator("line_start", "line_end")
    @classmethod
    def _positive_line_number(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Line numbers must be >= 1.")
        return v

    @model_validator(mode="after")
    def _end_gte_start(self) -> "SourceCitation":
        if self.line_end < self.line_start:
            raise ValueError(
                f"line_end ({self.line_end}) must be >= line_start ({self.line_start})."
            )
        return self
