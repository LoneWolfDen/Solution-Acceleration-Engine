"""Artifact Registry — in-memory store of MCP-ingested source files.

Design contracts
----------------
- Keyed by ``file_path`` (the path component of the MCP resource URI, after
  stripping the scheme prefix).  Re-registering the same path overwrites the
  prior entry, reflecting a refresh of that file's content.
- ``line_count`` is set by ``MCPHostClient.ingest_file()`` using
  ``str.splitlines()`` — the only approved counting method.  This ensures
  ``SourceCitation.line_end`` bounds remain within the actual file length
  (Property 7 / Property 8).
- ``build_context_string()`` produces the concatenated prompt context block
  consumed by ``PromptBuilder.build_dimension_prompt()``.
- ``scan_directory()`` provides a filesystem-based ingestion path for
  offline / test-artifact loading at startup (no MCP transport required).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── Data class ────────────────────────────────────────────────────────────────


@dataclass
class IngestedArtifact:
    """Represents a single source file that has been ingested via MCP or disk.

    Attributes
    ----------
    uri:
        The original MCP resource URI (e.g. ``"file:///path/to/doc.md"``).
    file_path:
        The path component of the URI, used as the registry key and as the
        ``file_path`` value in all ``SourceCitation`` objects referencing this
        file.
    content:
        Full raw text of the file.
    line_count:
        Number of lines as computed by ``len(content.splitlines())``.  Must
        be set by the ingestion caller — never recomputed inside this class to
        keep the counting authority unambiguous.
    """

    uri: str
    file_path: str
    content: str
    line_count: int


# ── Registry ──────────────────────────────────────────────────────────────────


class ArtifactRegistry:
    """In-memory store of ingested MCP artifacts, keyed by ``file_path``.

    Thread / task safety
    --------------------
    The registry is mutated only from the Textual asyncio event loop (single
    thread), so no locking is required.
    """

    def __init__(self) -> None:
        self._artifacts: Dict[str, IngestedArtifact] = {}

    # ── Mutation ──────────────────────────────────────────────────────────────

    def register(self, artifact: IngestedArtifact) -> None:
        """Add or replace the artifact entry for ``artifact.file_path``.

        Overwriting is intentional: a user may re-ingest a file after editing
        it, and the registry should always reflect the latest version.
        """
        self._artifacts[artifact.file_path] = artifact

    # ── Queries ───────────────────────────────────────────────────────────────

    def get(self, file_path: str) -> Optional[IngestedArtifact]:
        """Return the artifact for *file_path*, or ``None`` if not registered."""
        return self._artifacts.get(file_path)

    def all(self) -> List[IngestedArtifact]:
        """Return a snapshot list of all currently registered artifacts.

        The list is a shallow copy of the values view so that subsequent
        ``register()`` calls do not mutate an already-returned list.
        """
        return list(self._artifacts.values())

    def __len__(self) -> int:
        return len(self._artifacts)

    # ── Prompt context ────────────────────────────────────────────────────────

    def build_context_string(self) -> str:
        """Concatenate all artifact contents into a single prompt context block.

        Format::

            FILE: /path/to/file.md (42 lines)

            <file content>

            ---

            FILE: /path/to/other.txt (7 lines)

            <file content>

            ---

        Returns an empty string when no artifacts are registered (the
        ``make_dimension_runner`` guard checks for at least one artifact before
        allowing a Layer 1 run).
        """
        if not self._artifacts:
            return ""

        parts: List[str] = []
        for artifact in self._artifacts.values():
            parts.append(
                f"FILE: {artifact.file_path} ({artifact.line_count} lines)\n"
            )
            parts.append(artifact.content)
            parts.append("\n---\n")
        return "\n".join(parts)

    # ── Filesystem scanning ───────────────────────────────────────────────────

    def scan_directory(
        self,
        directory: "str | Path",
        extensions: Tuple[str, ...] = (".md", ".txt"),
    ) -> List[IngestedArtifact]:
        """Scan *directory* for text files and register each one.

        Reads every file whose suffix (case-insensitive) matches *extensions*,
        counts lines via ``str.splitlines()``, and registers an
        ``IngestedArtifact`` with ``uri = "file://<absolute_path>"``.

        Re-registering an already-known path overwrites the prior entry, so
        calling ``scan_directory()`` again after editing a file always reflects
        the latest content.

        Parameters
        ----------
        directory:
            Path to the directory to scan.  Non-existent or non-directory
            paths are silently ignored (returns an empty list) so the startup
            sequence never crashes when the path is absent.
        extensions:
            Tuple of lowercase file-extension strings to include.  Defaults
            to ``(".md", ".txt")``.

        Returns
        -------
        List[IngestedArtifact]
            Artifacts that were registered during this scan, in filesystem
            sort order.  Already-registered paths that were overwritten are
            included.
        """
        dir_path = Path(directory)
        if not dir_path.is_dir():
            return []

        registered: List[IngestedArtifact] = []
        for file_path in sorted(dir_path.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in extensions:
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            artifact = IngestedArtifact(
                uri=f"file://{file_path.resolve()}",
                file_path=str(file_path.resolve()),
                content=content,
                line_count=len(content.splitlines()),
            )
            self.register(artifact)
            registered.append(artifact)
        return registered
