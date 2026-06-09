"""MCP Host Client — stdio and SSE transport support with artifact ingestion.

Design contracts
----------------
- ``ingest_file(uri)`` counts lines exclusively via ``content.splitlines()``
  and passes the result directly into ``IngestedArtifact.line_count``.  This
  is the single authoritative counting site (Property 7).
- ``file_path`` stored in ``IngestedArtifact`` is derived from the URI by
  stripping the scheme prefix (everything up to and including ``://``).  All
  ``SourceCitation`` objects referencing that file must use this exact path
  (Property 8).
- On any transport connection failure, ``MCPIngestError`` is raised with the
  transport type in the message (Requirement 4.6).
- ``_session`` is ``None`` when no transport is active; ``ingest_file()`` and
  ``list_resources()`` fail fast with ``MCPIngestError`` in that state rather
  than silently returning empty results.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator, List, Optional

from .artifact_registry import ArtifactRegistry, IngestedArtifact

# MCP SDK imports are guarded so the module can be imported in test
# environments where the mcp package is available but a live server is not.
try:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
except ImportError as _mcp_import_error:  # pragma: no cover
    raise ImportError(
        "The 'mcp' package is required.  Install it with: pip install mcp"
    ) from _mcp_import_error


# ── Exception ─────────────────────────────────────────────────────────────────


class MCPIngestError(Exception):
    """Raised when an MCP transport connection fails or a resource read fails.

    The message always includes the transport type so that the TUI footer bar
    can surface a descriptive notification to the user (Requirement 4.6).
    """


# ── Client ────────────────────────────────────────────────────────────────────


class MCPHostClient:
    """MCP Host Client supporting stdio and SSE transports.

    Maintains a single active ``ClientSession`` at a time.  Connect via one of
    the async context managers (``connect_stdio`` or ``connect_sse``), then
    call ``ingest_file()`` or ``list_resources()`` within the ``async with``
    block.

    Parameters
    ----------
    registry:
        The shared ``ArtifactRegistry`` instance where ingested artifacts are
        stored.  Injected at construction so the registry lifetime is owned by
        the caller (typically ``ContextaApp``).
    """

    def __init__(self, registry: ArtifactRegistry) -> None:
        self._registry = registry
        self._session: Optional[ClientSession] = None

    # ── Transport context managers ────────────────────────────────────────────

    @asynccontextmanager
    async def connect_stdio(
        self,
        command: str,
        args: List[str],
    ) -> AsyncIterator[None]:
        """Connect to an MCP server via the stdio transport.

        Yields once the session is initialised and ready for resource
        operations.  Cleans up ``_session`` on exit even if an exception is
        raised inside the ``async with`` block.

        Parameters
        ----------
        command:
            Executable to launch as the MCP server process.
        args:
            Command-line arguments passed to *command*.

        Raises
        ------
        MCPIngestError
            If the stdio transport fails to connect or the session fails to
            initialise.
        """
        try:
            async with stdio_client(command, args) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    try:
                        yield
                    finally:
                        self._session = None
        except MCPIngestError:
            raise
        except Exception as exc:
            self._session = None
            raise MCPIngestError(
                f"stdio transport connection failed: {exc}"
            ) from exc

    @asynccontextmanager
    async def connect_sse(self, url: str) -> AsyncIterator[None]:
        """Connect to an MCP server via the SSE transport.

        Yields once the session is initialised and ready for resource
        operations.

        Parameters
        ----------
        url:
            HTTP(S) URL of the SSE endpoint exposed by the MCP server.

        Raises
        ------
        MCPIngestError
            If the SSE transport fails to connect or the session fails to
            initialise.
        """
        try:
            async with sse_client(url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    try:
                        yield
                    finally:
                        self._session = None
        except MCPIngestError:
            raise
        except Exception as exc:
            self._session = None
            raise MCPIngestError(
                f"SSE transport connection failed: {exc}"
            ) from exc

    # ── Resource operations ───────────────────────────────────────────────────

    async def ingest_file(self, uri: str) -> IngestedArtifact:
        """Read a resource from the connected MCP server and register it.

        Line counting uses ``str.splitlines()`` — the single authoritative
        method defined for this codebase (Property 7).  The ``file_path``
        stored in the returned ``IngestedArtifact`` is derived by stripping
        the URI scheme (``"<scheme>://"`` prefix), so all downstream
        ``SourceCitation`` objects referencing this file must use the same
        derivation (Property 8).

        Parameters
        ----------
        uri:
            MCP resource URI (e.g. ``"file:///home/user/proposal.md"``).

        Returns
        -------
        IngestedArtifact
            The registered artifact including content and line count.

        Raises
        ------
        MCPIngestError
            If no transport session is active, or if the resource read fails.
        """
        if self._session is None:
            raise MCPIngestError(
                "No active MCP transport connection — call connect_stdio() or "
                "connect_sse() before ingesting files"
            )

        try:
            result = await self._session.read_resource(uri)
        except Exception as exc:
            raise MCPIngestError(
                f"Failed to read MCP resource {uri!r}: {exc}"
            ) from exc

        try:
            content: str = result.contents[0].text
        except (AttributeError, IndexError) as exc:
            raise MCPIngestError(
                f"MCP resource {uri!r} returned an unexpected content shape: {exc}"
            ) from exc

        # Authoritative line-count calculation — splitlines() only.
        lines = content.splitlines()
        file_path = _uri_to_file_path(uri)

        artifact = IngestedArtifact(
            uri=uri,
            file_path=file_path,
            content=content,
            line_count=len(lines),
        )
        self._registry.register(artifact)
        return artifact

    async def list_resources(self) -> List[dict]:
        """List all resources available from the connected MCP server.

        Returns
        -------
        List[dict]
            Each element is the ``model_dump()`` of an MCP ``Resource`` object.

        Raises
        ------
        MCPIngestError
            If no transport session is active.
        """
        if self._session is None:
            raise MCPIngestError(
                "No active MCP transport connection — call connect_stdio() or "
                "connect_sse() before listing resources"
            )

        try:
            result = await self._session.list_resources()
        except Exception as exc:
            raise MCPIngestError(
                f"Failed to list MCP resources: {exc}"
            ) from exc

        return [r.model_dump() for r in result.resources]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _uri_to_file_path(uri: str) -> str:
    """Derive the ``file_path`` key from an MCP URI.

    Strips everything up to and including the first ``"://"`` separator.
    For URIs without a scheme (e.g. plain paths), the original string is
    returned unchanged.

    Examples
    --------
    >>> _uri_to_file_path("file:///home/user/doc.md")
    '/home/user/doc.md'
    >>> _uri_to_file_path("resource://server/data.txt")
    'server/data.txt'
    >>> _uri_to_file_path("/already/a/path.md")
    '/already/a/path.md'
    """
    marker = "://"
    idx = uri.find(marker)
    if idx == -1:
        return uri
    return uri[idx + len(marker):]
