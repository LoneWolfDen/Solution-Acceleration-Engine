"""Coverage gap tests — Sprint 2 modules.

Targets the uncovered lines in:
- ``contexta/llm/provider.py``:  LLMCallError paths, validate_backend()
- ``contexta/mcp/artifact_registry.py``: build_context_string() non-empty, __len__
- ``contexta/mcp/client.py``: transport error paths, list_resources(), ingest error paths
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contexta.llm.provider import (
    LLMCallError,
    LLMConfig,
    LLMResponse,
    call_llm,
    validate_backend,
)
from contexta.mcp.artifact_registry import ArtifactRegistry, IngestedArtifact
from contexta.mcp.client import MCPHostClient, MCPIngestError, _uri_to_file_path


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_mock_session(content: str = "line\n") -> MagicMock:
    content_item = MagicMock()
    content_item.text = content
    read_result = MagicMock()
    read_result.contents = [content_item]
    resource = MagicMock()
    resource.model_dump = MagicMock(return_value={"uri": "file:///test.md"})
    list_result = MagicMock()
    list_result.resources = [resource]
    session = MagicMock()
    session.read_resource = AsyncMock(return_value=read_result)
    session.list_resources = AsyncMock(return_value=list_result)
    return session


def _make_acompletion_mock(content: str = '{"ok": true}') -> AsyncMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    return AsyncMock(return_value=response)


# ── LLM provider error paths ──────────────────────────────────────────────────


class TestLLMCallErrorPaths:

    @pytest.mark.asyncio
    async def test_llmcallerror_on_acompletion_exception(self):
        """LLMCallError wraps any exception from litellm.acompletion."""
        failing_mock = AsyncMock(side_effect=RuntimeError("network timeout"))
        config = LLMConfig(model="ollama/mistral")
        with patch("contexta.llm.provider.litellm.acompletion", failing_mock):
            with pytest.raises(LLMCallError, match="network timeout"):
                await call_llm(config, system="s", user="u")

    @pytest.mark.asyncio
    async def test_llmcallerror_on_bad_response_shape(self):
        """LLMCallError raised when response lacks choices attribute."""
        bad_response = MagicMock(spec=[])  # no attributes at all
        bad_mock = AsyncMock(return_value=bad_response)
        config = LLMConfig(model="ollama/mistral")
        with patch("contexta.llm.provider.litellm.acompletion", bad_mock):
            with pytest.raises(LLMCallError, match="Unexpected LiteLLM response shape"):
                await call_llm(config, system="s", user="u")

    @pytest.mark.asyncio
    async def test_llmcallerror_on_empty_choices(self):
        """LLMCallError raised when choices list is empty."""
        response = MagicMock()
        response.choices = []
        bad_mock = AsyncMock(return_value=response)
        config = LLMConfig(model="ollama/mistral")
        with patch("contexta.llm.provider.litellm.acompletion", bad_mock):
            with pytest.raises(LLMCallError):
                await call_llm(config, system="s", user="u")

    @pytest.mark.asyncio
    async def test_llmcallerror_message_includes_model(self):
        """Error message names the failing model for easier debugging."""
        failing_mock = AsyncMock(side_effect=ConnectionError("refused"))
        config = LLMConfig(model="openai/gpt-4o")
        with patch("contexta.llm.provider.litellm.acompletion", failing_mock):
            with pytest.raises(LLMCallError, match="gpt-4o"):
                await call_llm(config, system="s", user="u")


class TestValidateBackend:

    def test_valid_ollama_backend(self):
        assert validate_backend("ollama/mistral") is True

    def test_valid_openai_backend(self):
        # openai is always registered with litellm
        result = validate_backend("openai/gpt-4o")
        assert isinstance(result, bool)

    def test_invalid_backend_no_slash_returns_false(self):
        # litellm.get_llm_provider raises on unknown format → False
        result = validate_backend("completelymadeup_backend_xyz_noslash")
        assert result is False

    def test_returns_bool_type(self):
        result = validate_backend("ollama/llama2")
        assert isinstance(result, bool)


# ── ArtifactRegistry coverage ─────────────────────────────────────────────────


class TestArtifactRegistryCoverage:

    def _make_artifact(self, path: str, content: str) -> IngestedArtifact:
        return IngestedArtifact(
            uri=f"file:///{path.lstrip('/')}",
            file_path=path,
            content=content,
            line_count=len(content.splitlines()),
        )

    def test_len_empty_registry(self):
        reg = ArtifactRegistry()
        assert len(reg) == 0

    def test_len_after_register(self):
        reg = ArtifactRegistry()
        reg.register(self._make_artifact("/a.md", "line\n"))
        assert len(reg) == 1

    def test_len_after_multiple_registers(self):
        reg = ArtifactRegistry()
        reg.register(self._make_artifact("/a.md", "a\n"))
        reg.register(self._make_artifact("/b.md", "b\n"))
        assert len(reg) == 2

    def test_len_overwrite_does_not_increase_count(self):
        reg = ArtifactRegistry()
        a = self._make_artifact("/same.md", "v1\n")
        reg.register(a)
        reg.register(self._make_artifact("/same.md", "v2\nv2b\n"))
        assert len(reg) == 1

    def test_build_context_string_single_artifact(self):
        reg = ArtifactRegistry()
        reg.register(self._make_artifact("/doc.md", "Hello\nWorld\n"))
        ctx = reg.build_context_string()
        assert "/doc.md" in ctx
        assert "2 lines" in ctx
        assert "Hello" in ctx
        assert "World" in ctx
        assert "---" in ctx

    def test_build_context_string_multiple_artifacts(self):
        reg = ArtifactRegistry()
        reg.register(self._make_artifact("/alpha.md", "alpha content\n"))
        reg.register(self._make_artifact("/beta.txt", "beta line1\nbeta line2\n"))
        ctx = reg.build_context_string()
        assert "/alpha.md" in ctx
        assert "/beta.txt" in ctx
        assert "alpha content" in ctx
        assert "beta line1" in ctx

    def test_build_context_string_empty_returns_empty(self):
        reg = ArtifactRegistry()
        assert reg.build_context_string() == ""

    def test_build_context_string_includes_line_count(self):
        reg = ArtifactRegistry()
        content = "a\nb\nc\nd\ne\n"
        reg.register(self._make_artifact("/five.md", content))
        ctx = reg.build_context_string()
        assert "5 lines" in ctx

    def test_all_returns_snapshot(self):
        reg = ArtifactRegistry()
        a = self._make_artifact("/snap.md", "snap\n")
        reg.register(a)
        snapshot = reg.all()
        # Mutating the registry after snapshot does not change snapshot
        reg.register(self._make_artifact("/new.md", "new\n"))
        assert len(snapshot) == 1


# ── MCPHostClient error/coverage paths ───────────────────────────────────────


class TestMCPHostClientErrorPaths:

    @pytest.mark.asyncio
    async def test_ingest_without_session_raises(self):
        """ingest_file() with no active session must raise MCPIngestError."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)
        with pytest.raises(MCPIngestError, match="No active MCP transport connection"):
            await client.ingest_file("file:///tmp/test.md")

    @pytest.mark.asyncio
    async def test_list_resources_without_session_raises(self):
        """list_resources() with no active session must raise MCPIngestError."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)
        with pytest.raises(MCPIngestError, match="No active MCP transport connection"):
            await client.list_resources()

    @pytest.mark.asyncio
    async def test_ingest_file_read_resource_exception_raises(self):
        """read_resource() failure is wrapped in MCPIngestError."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)
        session = MagicMock()
        session.read_resource = AsyncMock(side_effect=RuntimeError("read error"))
        client._session = session
        with pytest.raises(MCPIngestError, match="Failed to read MCP resource"):
            await client.ingest_file("file:///tmp/broken.md")

    @pytest.mark.asyncio
    async def test_ingest_file_bad_content_shape_raises(self):
        """Empty contents list raises MCPIngestError with shape message."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)
        read_result = MagicMock()
        read_result.contents = []  # no items → IndexError
        session = MagicMock()
        session.read_resource = AsyncMock(return_value=read_result)
        client._session = session
        with pytest.raises(MCPIngestError, match="unexpected content shape"):
            await client.ingest_file("file:///tmp/empty.md")

    @pytest.mark.asyncio
    async def test_list_resources_success(self):
        """list_resources() returns list of dicts from mock session."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)
        client._session = _make_mock_session()
        result = await client.list_resources()
        assert isinstance(result, list)
        assert result[0] == {"uri": "file:///test.md"}

    @pytest.mark.asyncio
    async def test_list_resources_exception_raises(self):
        """list_resources() wraps session errors in MCPIngestError."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)
        session = MagicMock()
        session.list_resources = AsyncMock(side_effect=RuntimeError("server error"))
        client._session = session
        with pytest.raises(MCPIngestError, match="Failed to list MCP resources"):
            await client.list_resources()

    @pytest.mark.asyncio
    async def test_connect_stdio_transport_failure_raises(self):
        """stdio transport failure raises MCPIngestError with 'stdio' in message."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)

        @asynccontextmanager
        async def _failing_stdio(cmd, args) -> AsyncIterator:
            raise ConnectionError("command not found")
            yield  # make it a generator

        with patch("contexta.mcp.client.stdio_client", _failing_stdio):
            with pytest.raises(MCPIngestError, match="stdio transport connection failed"):
                async with client.connect_stdio("nonexistent-cmd", []):
                    pass  # should not reach here

    @pytest.mark.asyncio
    async def test_connect_sse_transport_failure_raises(self):
        """SSE transport failure raises MCPIngestError with 'SSE' in message."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)

        @asynccontextmanager
        async def _failing_sse(url) -> AsyncIterator:
            raise ConnectionError("refused")
            yield  # make it a generator

        with patch("contexta.mcp.client.sse_client", _failing_sse):
            with pytest.raises(MCPIngestError, match="SSE transport connection failed"):
                async with client.connect_sse("http://localhost:9999/sse"):
                    pass  # should not reach here

    @pytest.mark.asyncio
    async def test_session_is_none_after_context_exit(self):
        """_session is reset to None after connect context exits normally."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)

        @asynccontextmanager
        async def _mock_stdio(cmd, args) -> AsyncIterator:
            read, write = MagicMock(), MagicMock()
            yield read, write

        mock_cs_instance = MagicMock()
        mock_cs_instance.__aenter__ = AsyncMock(return_value=mock_cs_instance)
        mock_cs_instance.__aexit__ = AsyncMock(return_value=False)
        mock_cs_instance.initialize = AsyncMock()

        with patch("contexta.mcp.client.stdio_client", _mock_stdio), \
             patch("contexta.mcp.client.ClientSession", return_value=mock_cs_instance):
            async with client.connect_stdio("cmd", []):
                assert client._session is mock_cs_instance

        assert client._session is None



# ── Transport happy-path and MCPIngestError re-raise ─────────────────────────


class TestTransportContextManagers:
    """Cover the inner finally block and MCPIngestError re-raise paths."""

    @pytest.mark.asyncio
    async def test_connect_stdio_session_cleared_on_normal_exit(self):
        """finally: self._session = None runs on normal context exit (line 109)."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)

        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()

        @asynccontextmanager
        async def _mock_stdio(cmd, args):
            yield MagicMock(), MagicMock()

        @asynccontextmanager
        async def _mock_cs(*a, **kw):
            yield mock_session

        with patch("contexta.mcp.client.stdio_client", _mock_stdio), \
             patch("contexta.mcp.client.ClientSession", return_value=MagicMock(
                 __aenter__=AsyncMock(return_value=mock_session),
                 __aexit__=AsyncMock(return_value=False),
             )):
            # Build a proper ClientSession mock using the class-level patch
            pass

        # Use the simpler approach: patch at class entry
        entered_session = None

        @asynccontextmanager
        async def _full_stdio(cmd, args):
            yield MagicMock(), MagicMock()

        class _FakeCS:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                return False

        with patch("contexta.mcp.client.stdio_client", _full_stdio), \
             patch("contexta.mcp.client.ClientSession", return_value=_FakeCS()):
            async with client.connect_stdio("cmd", []):
                assert client._session is mock_session

        assert client._session is None  # finally block ran

    @pytest.mark.asyncio
    async def test_connect_sse_session_cleared_on_normal_exit(self):
        """finally: self._session = None runs on normal SSE context exit (line 136-142)."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)

        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()

        @asynccontextmanager
        async def _full_sse(url):
            yield MagicMock(), MagicMock()

        class _FakeCS:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                return False

        with patch("contexta.mcp.client.sse_client", _full_sse), \
             patch("contexta.mcp.client.ClientSession", return_value=_FakeCS()):
            async with client.connect_sse("http://localhost/sse"):
                assert client._session is mock_session

        assert client._session is None

    @pytest.mark.asyncio
    async def test_connect_stdio_reraises_mcpingest_error(self):
        """MCPIngestError raised inside the with block is re-raised unchanged (line 112)."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)

        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()

        @asynccontextmanager
        async def _full_stdio(cmd, args):
            yield MagicMock(), MagicMock()

        class _FakeCS:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                return False

        original_error = MCPIngestError("inner error from caller")

        with patch("contexta.mcp.client.stdio_client", _full_stdio), \
             patch("contexta.mcp.client.ClientSession", return_value=_FakeCS()):
            with pytest.raises(MCPIngestError, match="inner error from caller"):
                async with client.connect_stdio("cmd", []):
                    raise original_error

    @pytest.mark.asyncio
    async def test_connect_sse_reraises_mcpingest_error(self):
        """MCPIngestError raised inside SSE block is re-raised unchanged (line 144)."""
        reg = ArtifactRegistry()
        client = MCPHostClient(reg)

        mock_session = MagicMock()
        mock_session.initialize = AsyncMock()

        @asynccontextmanager
        async def _full_sse(url):
            yield MagicMock(), MagicMock()

        class _FakeCS:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *args):
                return False

        with patch("contexta.mcp.client.sse_client", _full_sse), \
             patch("contexta.mcp.client.ClientSession", return_value=_FakeCS()):
            with pytest.raises(MCPIngestError, match="sse inner error"):
                async with client.connect_sse("http://localhost/sse"):
                    raise MCPIngestError("sse inner error")
