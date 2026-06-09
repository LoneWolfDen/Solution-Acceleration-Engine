"""Property 8 — Citation File Path Referential Integrity.

For any ingested artifact registered in the ``ArtifactRegistry`` with path
``P``, any ``SourceCitation`` generated that references that file must have
``file_path`` equal to ``P`` as recorded at ingestion time.

This module verifies:
1. The ``file_path`` stored by ``MCPHostClient.ingest_file()`` matches the
   path derived from the URI by ``_uri_to_file_path()``.
2. ``SourceCitation.file_path`` constructed from that path equals ``P``.
3. The Hypothesis property holds for arbitrary URI strings and citation
   combinations.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from contexta.mcp.artifact_registry import ArtifactRegistry, IngestedArtifact
from contexta.mcp.client import MCPHostClient, _uri_to_file_path
from contexta.models.citations import SourceCitation
from contexta.models.enums import CitationTypeEnum


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_mock_session(content: str = "line1\nline2\n") -> MagicMock:
    content_item = MagicMock()
    content_item.text = content
    read_result = MagicMock()
    read_result.contents = [content_item]
    session = MagicMock()
    session.read_resource = AsyncMock(return_value=read_result)
    return session


def _make_citation(file_path: str, line_start: int = 1, line_end: int = 2) -> SourceCitation:
    return SourceCitation(
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        citation_type=CitationTypeEnum.DIRECT_REFERENCE,
        excerpt="sample excerpt",
    )


# ── _uri_to_file_path unit tests ──────────────────────────────────────────────


class TestUriToFilePath:
    """Unit tests for the URI-to-path stripping helper."""

    def test_file_scheme(self):
        assert _uri_to_file_path("file:///home/user/doc.md") == "/home/user/doc.md"

    def test_resource_scheme(self):
        assert _uri_to_file_path("resource://server/data.txt") == "server/data.txt"

    def test_no_scheme(self):
        assert _uri_to_file_path("/already/a/path.md") == "/already/a/path.md"

    def test_custom_scheme(self):
        assert _uri_to_file_path("mcp://host/proposal.docx") == "host/proposal.docx"

    def test_double_slash_in_path(self):
        uri = "file:///var//data/notes.txt"
        expected = "/var//data/notes.txt"
        assert _uri_to_file_path(uri) == expected

    def test_empty_path_after_scheme(self):
        uri = "file://"
        assert _uri_to_file_path(uri) == ""


# ── Referential integrity unit tests ─────────────────────────────────────────


class TestCitationFilePathIntegrity:
    """Verify that SourceCitation.file_path matches the registered artifact path."""

    @pytest.mark.asyncio
    async def test_citation_path_matches_registered_artifact(self):
        """After ingesting a file, citations referencing it use the registered path."""
        uri = "file:///workspace/proposal.md"
        registry = ArtifactRegistry()
        client = MCPHostClient(registry)
        client._session = _make_mock_session("line one\nline two\n")

        artifact = await client.ingest_file(uri)
        registered_path = artifact.file_path

        citation = _make_citation(registered_path)
        assert citation.file_path == registered_path

    @pytest.mark.asyncio
    async def test_file_path_equals_uri_stripped(self):
        """file_path is always the URI with the scheme prefix removed."""
        uri = "file:///docs/requirements.txt"
        registry = ArtifactRegistry()
        client = MCPHostClient(registry)
        client._session = _make_mock_session("req1\nreq2\n")

        artifact = await client.ingest_file(uri)
        assert artifact.file_path == _uri_to_file_path(uri)
        assert artifact.file_path == "/docs/requirements.txt"

    @pytest.mark.asyncio
    async def test_multiple_files_citations_stay_isolated(self):
        """Citations for different files never share a file_path."""
        uris = [
            "file:///a/alpha.md",
            "file:///b/beta.md",
            "file:///c/gamma.md",
        ]
        registry = ArtifactRegistry()
        client = MCPHostClient(registry)
        artifacts = []
        for uri in uris:
            client._session = _make_mock_session(f"content for {uri}")
            artifacts.append(await client.ingest_file(uri))

        paths = [a.file_path for a in artifacts]
        assert len(set(paths)) == 3  # all distinct

        for artifact in artifacts:
            citation = _make_citation(artifact.file_path)
            assert citation.file_path == artifact.file_path
            assert registry.get(citation.file_path) is not None

    @pytest.mark.asyncio
    async def test_registry_lookup_by_citation_path_always_succeeds(self):
        """``registry.get(citation.file_path)`` must return the artifact, not None."""
        uri = "file:///project/design.md"
        registry = ArtifactRegistry()
        client = MCPHostClient(registry)
        client._session = _make_mock_session("design content\n")

        artifact = await client.ingest_file(uri)
        citation = _make_citation(artifact.file_path)

        looked_up = registry.get(citation.file_path)
        assert looked_up is not None
        assert looked_up.file_path == citation.file_path
        assert looked_up.uri == uri

    @pytest.mark.asyncio
    async def test_citation_lines_within_artifact_bounds(self):
        """SourceCitation line bounds must not exceed the artifact line_count."""
        content = "a\nb\nc\nd\ne\n"  # 5 lines
        registry = ArtifactRegistry()
        client = MCPHostClient(registry)
        client._session = _make_mock_session(content)
        artifact = await client.ingest_file("file:///tmp/five_lines.txt")

        # Valid citation: within bounds
        valid = SourceCitation(
            file_path=artifact.file_path,
            line_start=1,
            line_end=artifact.line_count,
            citation_type=CitationTypeEnum.DIRECT_REFERENCE,
            excerpt="excerpt",
        )
        assert valid.line_start <= valid.line_end <= artifact.line_count


# ── Hypothesis property test ──────────────────────────────────────────────────


@given(
    path_suffix=st.text(
        alphabet=st.characters(blacklist_characters="\x00"),
        min_size=1,
        max_size=200,
    ),
    content=st.text(min_size=1),
)
@settings(max_examples=300)
def test_property_8_citation_file_path_matches_registered_path(
    path_suffix: str,
    content: str,
) -> None:
    """Property 8: citation.file_path == registered artifact.file_path for any URI.

    Constructs a URI, ingests the artifact synchronously, creates a
    ``SourceCitation`` using the registered path, and asserts equality.
    """
    # Build a URI from the generated suffix (sanitise for URI use)
    uri = f"file:///{path_suffix.lstrip('/')}"

    async def _run() -> None:
        registry = ArtifactRegistry()
        client = MCPHostClient(registry)
        client._session = _make_mock_session(content)
        artifact = await client.ingest_file(uri)

        # The registered path must match what _uri_to_file_path produces
        expected_path = _uri_to_file_path(uri)
        assert artifact.file_path == expected_path, (
            f"artifact.file_path={artifact.file_path!r} != "
            f"expected_path={expected_path!r} for uri={uri!r}"
        )

        # A citation using that path must be retrievable from the registry
        lines = content.splitlines()
        line_count = len(lines)
        if line_count >= 1:
            citation = SourceCitation(
                file_path=artifact.file_path,
                line_start=1,
                line_end=max(1, line_count),
                citation_type=CitationTypeEnum.DIRECT_REFERENCE,
                excerpt="test",
            )
            assert citation.file_path == artifact.file_path
            looked_up = registry.get(citation.file_path)
            assert looked_up is not None
            assert looked_up.file_path == citation.file_path

    asyncio.run(_run())
