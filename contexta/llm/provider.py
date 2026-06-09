"""LiteLLM provider abstraction layer.

This module is the **only** place in the codebase that calls ``litellm``.

Temperature-Zero Mode
---------------------
Every call to ``call_llm()`` unconditionally passes:
  - ``temperature=0.0``   — eliminates non-deterministic sampling variation
  - ``response_format={"type": "json_object"}`` — requests structured JSON output

These two overrides are applied inside ``call_llm()`` itself; callers have no
mechanism to override them.  This satisfies Requirement 5.2 / 6.2 and is
verified by Property 10 (Temperature-Zero LLM Call Invariant).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import litellm


# ── Exceptions ────────────────────────────────────────────────────────────────


class LLMCallError(Exception):
    """Raised when a LiteLLM call fails (network, non-200, or unexpected shape)."""


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class LLMConfig:
    """Runtime configuration for a LiteLLM-backed model.

    ``model`` must be a LiteLLM-compatible backend identifier such as
    ``"ollama/mistral"`` or ``"openai/gpt-4o"``.
    """

    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@dataclass
class LLMResponse:
    """Structured result of a single LiteLLM completion call."""

    content: str
    raw_response: Any
    finish_reason: str


# ── Public API ────────────────────────────────────────────────────────────────

#: Temperature value enforced on every LLM call — never changes.
_TEMPERATURE: float = 0.0

#: Response format enforced on every LLM call — never changes.
_RESPONSE_FORMAT: dict = {"type": "json_object"}


async def call_llm(
    config: LLMConfig,
    system: str,
    user: str,
    max_tokens: int = 4096,
) -> LLMResponse:
    """Make a single LiteLLM completion call in Temperature-Zero Mode.

    Parameters
    ----------
    config:
        LLM backend configuration (model, optional api_key / base_url).
    system:
        System-role message — assembled by ``PromptBuilder``.
    user:
        User-role message — typically the artifact context block.
    max_tokens:
        Upper bound on the completion length.

    Returns
    -------
    LLMResponse
        Parsed content and raw LiteLLM response object.

    Raises
    ------
    LLMCallError
        On any network failure, non-200 status, or unexpected response shape.
    """
    kwargs: dict = dict(
        model=config.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=_TEMPERATURE,
        response_format=_RESPONSE_FORMAT,
        max_tokens=max_tokens,
    )
    if config.api_key is not None:
        kwargs["api_key"] = config.api_key
    if config.base_url is not None:
        kwargs["base_url"] = config.base_url

    try:
        response = await litellm.acompletion(**kwargs)
    except Exception as exc:
        raise LLMCallError(f"LiteLLM call failed for model {config.model!r}: {exc}") from exc

    try:
        content: str = response.choices[0].message.content
        finish_reason: str = response.choices[0].finish_reason
    except (AttributeError, IndexError) as exc:
        raise LLMCallError(
            f"Unexpected LiteLLM response shape for model {config.model!r}: {exc}"
        ) from exc

    return LLMResponse(
        content=content,
        raw_response=response,
        finish_reason=finish_reason,
    )


def validate_backend(backend: str) -> bool:
    """Return ``True`` if LiteLLM recognises *backend* as a valid provider string.

    Uses ``litellm.get_llm_provider()`` internally; returns ``False`` (rather
    than propagating) on any exception so callers can treat this as a simple
    boolean guard.
    """
    try:
        litellm.get_llm_provider(backend)
        return True
    except Exception:
        return False
