"""Property 7 — Artifact Line Count Accuracy.

For any string representing file content (with any number of lines, including
zero), the ``IngestedArtifact.line_count`` registered by the client must equal
``len(content.splitlines())``.

This test module covers both:
- Unit tests with hand-crafted edge cases (empty string, single line, CRLF,
  mixed endings, trailing newline, Unicode).
- A Hypothesis property test that generates arbitrary text and asserts the
  invariant holds for all inputs.

The MCP session is mocked so no live server is needed.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contexta.mcp.artifact_registry import ArtifactRegistry, IngestedArtifact
from contexta.mcp.client import MCPHostClient, _uri_to_file_path


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_mock_session(content: str) -> MagicMock:
    """Return a mock ClientSession whose read_resource() returns *content*."""
    content_item = MagicMock()
    content_item.text = content

    read_result = MagicMock()
    read_result.contents = [content_item]

    session = MagicMock()
    session.read_resource = AsyncMock(return_value=read_result)
    return session


async def _ingest_with_content(content: str, uri: str = "file:///tmp/test.md") -> IngestedArtifact:
    """Ingest *content* via a mocked MCPHostClient and return the artifact."""
    registry = ArtifactRegistry()
    client = MCPHostClient(registry)
    client._session = _make_mock_session(content)
    return await client.ingest_file(uri)


# ── Unit tests — edge cases ───────────────────────────────────────────────────


class TestLineCountEdgeCases:
    """Hand-crafted edge cases that must always pass regardless of Hypothesis."""

    @pytest.mark.asyncio
    async def test_empty_string(self):
        """Empty content has zero lines (splitlines() returns [])."""
        artifact = await _ingest_with_content("")
        assert artifact.line_count == 0
        assert artifact.line_count == len("".splitlines())

    @pytest.mark.asyncio
    async def test_single_line_no_newline(self):
        content = "Hello, world!"
        artifact = await _ingest_with_content(content)
        assert artifact.line_count == len(content.splitlines())

    @pytest.mark.asyncio
    async def test_single_line_with_trailing_newline(self):
        content = "Hello, world!\n"
        artifact = await _ingest_with_content(content)
        assert artifact.line_count == len(content.splitlines())

    @pytest.mark.asyncio
    async def test_multiple_lines_lf(self):
        content = "line one\nline two\nline three"
        artifact = await _ingest_with_content(content)
        assert artifact.line_count == 3
        assert artifact.line_count == len(content.splitlines())

    @pytest.mark.asyncio
    async def test_multiple_lines_crlf(self):
        content = "line one\r\nline two\r\nline three\r\n"
        artifact = await _ingest_with_content(content)
        assert artifact.line_count == len(content.splitlines())

    @pytest.mark.asyncio
    async def test_multiple_lines_mixed_endings(self):
        content = "alpha\nbeta\r\ngamma\rδ"
        artifact = await _ingest_with_content(content)
        assert artifact.line_count == len(content.splitlines())

    @pytest.mark.asyncio
    async def test_only_newlines(self):
        content = "\n\n\n"
        artifact = await _ingest_with_content(content)
        assert artifact.line_count == len(content.splitlines())

    @pytest.mark.asyncio
    async def test_unicode_content(self):
        content = "日本語\n中文\nEnglish\n한국어"
        artifact = await _ingest_with_content(content)
        assert artifact.line_count == 4
        assert artifact.line_count == len(content.splitlines())

    @pytest.mark.asyncio
    async def test_large_content(self):
        """1 000-line file counts correctly."""
        lines = [f"line {i}" for i in range(1000)]
        content = "\n".join(lines)
        artifact = await _ingest_with_content(content)
        assert artifact.line_count == 1000
        assert artifact.line_count == len(content.splitlines())

    @pytest.mark.asyncio
    async def test_line_count_stored_in_registry(self):
        """Registry entry has the same line_count as the returned artifact."""
        content = "a\nb\nc\n"
        registry = ArtifactRegistry()
        client = MCPHostClient(registry)
        client._session = _make_mock_session(content)
        artifact = await client.ingest_file("file:///tmp/doc.txt")
        stored = registry.get(artifact.file_path)
        assert stored is not None
        assert stored.line_count == artifact.line_count

    @pytest.mark.asyncio
    async def test_overwrite_updates_line_count(self):
        """Re-ingesting the same URI with new content updates line_count."""
        registry = ArtifactRegistry()
        client = MCPHostClient(registry)
        uri = "file:///tmp/evolving.md"

        client._session = _make_mock_session("v1\n")
        a1 = await client.ingest_file(uri)
        assert a1.line_count == 1

        client._session = _make_mock_session("v2\nline2\nline3\n")
        a2 = await client.ingest_file(uri)
        assert a2.line_count == 3
        assert registry.get(a2.file_path).line_count == 3


# ── Hypothesis property test ──────────────────────────────────────────────────


@given(content=st.text())
@settings(max_examples=500)
def test_property_7_line_count_matches_splitlines(content: str):
    """Property 7: line_count == len(content.splitlines()) for ALL text inputs.

    Synchronous wrapper around the async ingest path; uses asyncio.run() so
    Hypothesis can drive it without requiring pytest-asyncio's async test
    support (which doesn't compose with @given).
    """
    artifact = asyncio.run(_ingest_with_content(content))
    assert artifact.line_count == len(content.splitlines()), (
        f"line_count={artifact.line_count} but splitlines()={len(content.splitlines())} "
        f"for content={content!r}"
    )
