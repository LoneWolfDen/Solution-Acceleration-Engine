"""Property 22 — Citation Jump Target Accuracy.

For any ``IssueFinding`` with at least one ``SourceCitation``, when that
finding is selected in ``PipelineView``, the ``CitationJumpRequested`` message
emitted must carry ``file_path``, ``line_start``, and ``line_end`` values that
exactly match ``finding.citations[0]``.

This module covers:

1. **Unit tests** — ``PipelineView.select_finding()`` produces a
   ``CitationJumpRequested`` whose fields match the first citation exactly.
2. **No-citation guard** — selecting a finding with an empty citations list
   must not emit any message.
3. **Multi-citation precedence** — only ``citations[0]`` drives the jump; all
   other citations are ignored.
4. **Hypothesis property test** — for arbitrary valid ``IssueFinding`` objects
   with at least one citation, the message always carries the correct values.
5. **Integration (live app)** — ``select_finding()`` on a mounted
   ``PipelineView`` delivers a ``CitationJumpRequested`` with matching fields.

Validates: Requirements 10.8, 10.9, Design §11 Property 22.
"""

from __future__ import annotations

import asyncio
from typing import List
from unittest.mock import MagicMock, patch

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
from contexta.tui.messages import CitationJumpRequested
from contexta.tui.widgets.pipeline_view import PipelineView


# ── Factories ─────────────────────────────────────────────────────────────────


def _make_citation(
    file_path: str = "/docs/proposal.md",
    line_start: int = 10,
    line_end: int = 20,
) -> SourceCitation:
    return SourceCitation(
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
        excerpt="sample excerpt",
    )


def _make_finding(
    citations: List[SourceCitation],
    dimension: ReviewDimensionEnum = ReviewDimensionEnum.RISK,
    confidence: ConfidenceEnum = ConfidenceEnum.RED,
) -> IssueFinding:
    return IssueFinding(
        dimension=dimension,
        confidence=confidence,
        summary="Test finding",
        detail="Detailed description of the finding.",
        citations=citations,
        mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
    )


# ── Unit: select_finding() message construction ───────────────────────────────


class TestSelectFindingMessageContent:
    """select_finding() must produce a CitationJumpRequested matching citations[0]."""

    def _capture_jump(self, finding: IssueFinding) -> CitationJumpRequested | None:
        """Run select_finding() and capture the posted message."""
        pv = PipelineView()
        captured: list[CitationJumpRequested] = []

        original_post = pv.post_message

        def _intercept(msg):
            if isinstance(msg, CitationJumpRequested):
                captured.append(msg)
            # Do not call original_post (no app to dispatch to in unit context).

        pv.post_message = _intercept  # type: ignore[method-assign]
        pv.select_finding(finding)
        return captured[0] if captured else None

    def test_file_path_matches_citations_0(self):
        citation = _make_citation(file_path="/workspace/scope.md", line_start=5, line_end=10)
        finding = _make_finding(citations=[citation])
        msg = self._capture_jump(finding)
        assert msg is not None
        assert msg.file_path == citation.file_path

    def test_line_start_matches_citations_0(self):
        citation = _make_citation(line_start=42, line_end=55)
        finding = _make_finding(citations=[citation])
        msg = self._capture_jump(finding)
        assert msg is not None
        assert msg.line_start == citation.line_start

    def test_line_end_matches_citations_0(self):
        citation = _make_citation(line_start=1, line_end=99)
        finding = _make_finding(citations=[citation])
        msg = self._capture_jump(finding)
        assert msg is not None
        assert msg.line_end == citation.line_end

    def test_all_three_fields_match_simultaneously(self):
        """File path, line_start, and line_end all match in the same call."""
        citation = _make_citation(
            file_path="/contracts/sow.docx",
            line_start=100,
            line_end=115,
        )
        finding = _make_finding(citations=[citation])
        msg = self._capture_jump(finding)
        assert msg is not None
        assert msg.file_path == "/contracts/sow.docx"
        assert msg.line_start == 100
        assert msg.line_end == 115

    def test_single_line_citation_start_equals_end(self):
        """line_start == line_end is valid (single-line citation)."""
        citation = _make_citation(line_start=7, line_end=7)
        finding = _make_finding(citations=[citation])
        msg = self._capture_jump(finding)
        assert msg is not None
        assert msg.line_start == 7
        assert msg.line_end == 7

    def test_no_message_when_citations_empty(self):
        """select_finding() with zero citations must not emit any message."""
        finding = _make_finding(citations=[])
        msg = self._capture_jump(finding)
        assert msg is None, "Expected no CitationJumpRequested for a finding with no citations"

    def test_only_first_citation_drives_jump(self):
        """When a finding has multiple citations, only citations[0] is used."""
        c0 = _make_citation(file_path="/first.md", line_start=1, line_end=5)
        c1 = _make_citation(file_path="/second.md", line_start=10, line_end=20)
        c2 = _make_citation(file_path="/third.md", line_start=30, line_end=40)
        finding = _make_finding(citations=[c0, c1, c2])
        msg = self._capture_jump(finding)
        assert msg is not None
        assert msg.file_path == c0.file_path
        assert msg.line_start == c0.line_start
        assert msg.line_end == c0.line_end

    @pytest.mark.parametrize("dimension", list(ReviewDimensionEnum))
    def test_citation_jump_works_for_all_dimensions(self, dimension: ReviewDimensionEnum):
        """CitationJumpRequested is emitted regardless of which dimension owns the finding."""
        citation = _make_citation(file_path=f"/{dimension.value.lower()}.md", line_start=1, line_end=3)
        finding = _make_finding(citations=[citation], dimension=dimension)
        msg = self._capture_jump(finding)
        assert msg is not None
        assert msg.file_path == citation.file_path

    def test_message_type_is_citation_jump_requested(self):
        """The emitted message is an instance of CitationJumpRequested."""
        citation = _make_citation()
        finding = _make_finding(citations=[citation])
        msg = self._capture_jump(finding)
        assert isinstance(msg, CitationJumpRequested)

    def test_line_end_gte_line_start_invariant_preserved(self):
        """The message line_end is always >= line_start (mirroring SourceCitation)."""
        citation = _make_citation(line_start=50, line_end=50)
        finding = _make_finding(citations=[citation])
        msg = self._capture_jump(finding)
        assert msg is not None
        assert msg.line_end >= msg.line_start


# ── Unit: load_findings + select_finding sequence ────────────────────────────


class TestLoadFindingsSelectSequence:
    """load_findings() stores findings; select_finding() uses them correctly."""

    def test_load_findings_stores_correct_count(self):
        pv = PipelineView()
        findings = [
            _make_finding(citations=[_make_citation(line_start=i, line_end=i + 5)])
            for i in range(1, 6)
        ]
        pv.load_findings(findings)
        assert len(pv._findings) == 5

    def test_select_first_finding_from_loaded_list(self):
        pv = PipelineView()
        target_citation = _make_citation(file_path="/target.md", line_start=20, line_end=30)
        findings = [_make_finding(citations=[target_citation])]
        pv.load_findings(findings)

        captured: list = []
        pv.post_message = lambda m: captured.append(m)  # type: ignore[method-assign]

        pv.select_finding(pv._findings[0])
        assert len(captured) == 1
        msg = captured[0]
        assert msg.file_path == "/target.md"
        assert msg.line_start == 20
        assert msg.line_end == 30


# ── Hypothesis property test ──────────────────────────────────────────────────


def _citation_from_pair(file_path: str, line_start: int, line_end: int) -> SourceCitation:
    """Build a SourceCitation with guaranteed line_end >= line_start."""
    lo = min(line_start, line_end)
    hi = max(line_start, line_end)
    return SourceCitation(
        file_path=file_path,
        line_start=lo,
        line_end=hi,
        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
        excerpt="sample excerpt",
    )


_citation_strategy = st.builds(
    _citation_from_pair,
    file_path=st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(blacklist_characters="\x00\n\r"),
    ).map(lambda s: "/" + s.lstrip("/")),
    line_start=st.integers(min_value=1, max_value=9999),
    line_end=st.integers(min_value=1, max_value=9999),
)

_extra_citations_strategy = st.lists(_citation_strategy, min_size=0, max_size=5)


@given(
    primary=_citation_strategy,
    extras=_extra_citations_strategy,
    dimension=st.sampled_from(list(ReviewDimensionEnum)),
    confidence=st.sampled_from(list(ConfidenceEnum)),
)
@settings(max_examples=400)
def test_property_22_citation_jump_target_accuracy(
    primary: SourceCitation,
    extras: list[SourceCitation],
    dimension: ReviewDimensionEnum,
    confidence: ConfidenceEnum,
) -> None:
    """Property 22: CitationJumpRequested always carries citations[0] values.

    For ANY valid IssueFinding with at least one SourceCitation, the message
    emitted by ``PipelineView.select_finding()`` must carry:
    - ``file_path  == finding.citations[0].file_path``
    - ``line_start == finding.citations[0].line_start``
    - ``line_end   == finding.citations[0].line_end``
    """
    all_citations = [primary] + extras
    finding = IssueFinding(
        dimension=dimension,
        confidence=confidence,
        summary="Hypothesis finding",
        detail="Generated by Hypothesis for property testing.",
        citations=all_citations,
        mitigation_routing=MitigationRoutingEnum.RISK_REGISTER,
    )

    pv = PipelineView()
    captured: list[CitationJumpRequested] = []
    pv.post_message = lambda m: (  # type: ignore[method-assign]
        captured.append(m) if isinstance(m, CitationJumpRequested) else None
    )
    pv.select_finding(finding)

    assert len(captured) == 1, (
        f"Expected exactly 1 CitationJumpRequested, got {len(captured)}"
    )
    msg = captured[0]
    c0 = finding.citations[0]

    assert msg.file_path == c0.file_path, (
        f"file_path mismatch: {msg.file_path!r} != {c0.file_path!r}"
    )
    assert msg.line_start == c0.line_start, (
        f"line_start mismatch: {msg.line_start} != {c0.line_start}"
    )
    assert msg.line_end == c0.line_end, (
        f"line_end mismatch: {msg.line_end} != {c0.line_end}"
    )


# ── Integration: live app CitationJumpRequested routing ───────────────────────


class TestCitationJumpIntegration:
    """End-to-end: select_finding() in a mounted app emits the correct message."""

    @pytest.mark.asyncio
    async def test_select_finding_emits_citation_jump_in_live_app(self):
        """In a running app, select_finding() produces the right CitationJumpRequested."""
        from contexta.tui.app import ContextaApp

        citation = _make_citation(
            file_path="/live/test/document.md",
            line_start=25,
            line_end=35,
        )
        finding = _make_finding(citations=[citation])

        received: list[CitationJumpRequested] = []

        def _hook(msg):
            if isinstance(msg, CitationJumpRequested):
                received.append(msg)

        app = ContextaApp()
        async with app.run_test(
            headless=True,
            size=(120, 40),
            message_hook=_hook,
        ) as pilot:
            await pilot.pause(0.2)
            pv = app.screen.query_one(PipelineView)
            pv.select_finding(finding)
            await pilot.pause(0.1)

        assert len(received) >= 1, "CitationJumpRequested was not received by message_hook"
        msg = received[0]
        assert msg.file_path == citation.file_path
        assert msg.line_start == citation.line_start
        assert msg.line_end == citation.line_end
