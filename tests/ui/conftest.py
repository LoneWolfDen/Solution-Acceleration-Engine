"""tests/ui/conftest.py — Shared helpers for Milestone 6 component tests.

Design approach
---------------
Reflex components are pure Python objects: calling a component function
produces an rx.Component tree without running a server or a browser.
These tests verify:

  1. **Smoke** — component functions return rx.Component without raising.
  2. **Structure** — the component tree contains the expected widget types
     (rx.foreach for data-driven lists, rx.switch for toggles, etc.).
  3. **Event wiring** — event_triggers on key widgets reference the correct
     AppState event handlers via ``EventHandler.fn``.
  4. **State defaults** — AppState class-level field defaults match the values
     that components depend on (e.g. empty strings, False, "Version 1").

Tests run in isolation: no live server, no browser, no API calls.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest
import reflex as rx

from web.state import AppState


# ---------------------------------------------------------------------------
# Component tree helpers
# ---------------------------------------------------------------------------


def collect_types(comp: rx.Component) -> Counter:
    """Return a Counter of component type names found in the whole tree."""
    counts: Counter = Counter()

    def _walk(c: Any) -> None:
        counts[type(c).__name__] += 1
        for child in getattr(c, "children", []):
            _walk(child)

    _walk(comp)
    return counts


def find_by_type(comp: rx.Component, type_name: str) -> list[Any]:
    """Return all descendant components with the given type name."""
    results: list[Any] = []

    def _walk(c: Any) -> None:
        if type(c).__name__ == type_name:
            results.append(c)
        for child in getattr(c, "children", []):
            _walk(child)

    _walk(comp)
    return results


def event_handler_fn(event_trigger_chain: Any) -> Any:
    """Extract the underlying state function from an EventChain trigger value.

    EventChain.events[0].handler.fn gives the original Python function.
    Returns None if the chain is empty or not structured as expected.
    """
    events = getattr(event_trigger_chain, "events", [])
    if not events:
        return None
    handler = getattr(events[0], "handler", None)
    return getattr(handler, "fn", None)


# ---------------------------------------------------------------------------
# AppState field-default access
# ---------------------------------------------------------------------------


def state_default(field_name: str) -> Any:
    """Return the declared default value for an AppState field.

    List fields use ``default_factory`` and return a fresh empty list here.
    """
    import dataclasses

    field = AppState.__fields__[field_name]
    if isinstance(field.default, dataclasses._MISSING_TYPE):
        factory = getattr(field, "default_factory", None)
        return factory() if factory is not None else None
    return field.default


# ---------------------------------------------------------------------------
# Mock finding dict factory
# ---------------------------------------------------------------------------

MOCK_FINDING: dict = {
    "finding_id": "f-001",
    "type": "RISK",
    "severity": "HIGH",
    "text": "The solution lacks a disaster recovery plan.",
    "source_artifact": "architecture.md",
    "citation": "",
}

MOCK_FINDING_WITH_CITATION: dict = {
    **MOCK_FINDING,
    "finding_id": "f-002",
    "citation": "line 42: 'No DR strategy defined'",
}

MOCK_ARTIFACT: dict = {
    "artifact_id": "art-001",
    "title": "Architecture Doc",
    "tags": ["architecture", "risk"],
    "is_active": True,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_finding() -> dict:
    return dict(MOCK_FINDING)


@pytest.fixture()
def mock_finding_with_citation() -> dict:
    return dict(MOCK_FINDING_WITH_CITATION)


@pytest.fixture()
def mock_artifact() -> dict:
    return dict(MOCK_ARTIFACT)
