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

Rate-limit handling
-------------------
``_call_llm_with_retry()`` wraps the raw litellm call with:
  - Up to ``MAX_RETRY_ATTEMPTS`` retries on ``RateLimitError``.
  - Exponential back-off with jitter drawn from ``_jitter()``.
  - A global ``asyncio.Semaphore`` (``_LLM_SEMAPHORE``) that caps the number of
    concurrent in-flight LLM requests to ``MAX_CONCURRENT_LLM_REQUESTS``.  This
    prevents burst parallelism (e.g. 12 simultaneous dimension calls) from
    immediately exhausting the provider's TPM ceiling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from typing import Any, Optional

import litellm

logger = logging.getLogger(__name__)


# ── Concurrency cap ───────────────────────────────────────────────────────────

#: Maximum number of LLM calls allowed in-flight at the same time.
#: Set to 1 so that sequential dimension tasks never overlap;
#: increase to 2-3 if the provider supports higher parallel throughput.
MAX_CONCURRENT_LLM_REQUESTS: int = 1

#: The semaphore instance.  Created lazily on first use so it is always bound
#: to the running event loop (avoids "attached to a different loop" errors in
#: pytest where a new loop is created per test).
_LLM_SEMAPHORE: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    """Return the module-level semaphore, creating it on the current loop if needed."""
    global _LLM_SEMAPHORE
    if _LLM_SEMAPHORE is None:
        _LLM_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_LLM_REQUESTS)
    return _LLM_SEMAPHORE


def reset_semaphore() -> None:
    """Re-create the semaphore.  Call this in test teardown to avoid loop contamination."""
    global _LLM_SEMAPHORE
    _LLM_SEMAPHORE = None


# ── Retry parameters ──────────────────────────────────────────────────────────

#: Total attempts including the first — so ``MAX_RETRY_ATTEMPTS=5`` means 1
#: initial attempt + 4 retries.
MAX_RETRY_ATTEMPTS: int = 5

#: Base delay in seconds for the exponential back-off.
_RETRY_BASE_DELAY: float = 2.0

#: Maximum delay cap in seconds — prevents unbounded waits.
_RETRY_MAX_DELAY: float = 60.0


def _backoff_delay(attempt: int) -> float:
    """Compute exponential back-off with ±20 % uniform jitter.

    ``attempt`` is 0-indexed (0 = first retry, 1 = second, …).
    """
    base = min(_RETRY_BASE_DELAY * (2 ** attempt), _RETRY_MAX_DELAY)
    jitter = base * 0.2 * (random.random() * 2 - 1)  # ±20 %
    return max(0.1, base + jitter)


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


# ── JSON normalisation ────────────────────────────────────────────────────────


def _normalise_json_content(raw: str, model: str) -> str:
    """Unwrap a JSON array to its first dict element.

    Groq occasionally violates the ``response_format={"type": "json_object"}``
    contract by wrapping the requested object inside a JSON array, e.g.::

        [{"dimension": "NFR", "findings": [...], ...}]

    This pre-processor ensures the ``LLMResponse.content`` field always
    contains a plain JSON *object* so that downstream
    ``ReviewNodePayload.model_validate_json()`` never receives a list.
    """
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMCallError(
            f"Model {model!r} returned non-JSON content: {exc}"
        ) from exc

    if isinstance(parsed, list):
        logger.warning(
            "Model %r returned a JSON array instead of an object — "
            "unwrapping first element (array length=%d).",
            model,
            len(parsed),
        )
        if not parsed:
            raise LLMCallError(
                f"Model {model!r} returned an empty JSON array; "
                "cannot extract a ReviewNodePayload."
            )
        first = parsed[0]
        if not isinstance(first, dict):
            raise LLMCallError(
                f"Model {model!r} returned a JSON array whose first element is "
                f"{type(first).__name__!r}, not a dict; cannot extract payload."
            )
        return json.dumps(first)

    if not isinstance(parsed, dict):
        raise LLMCallError(
            f"Model {model!r} returned JSON of unexpected type "
            f"{type(parsed).__name__!r}; expected a dict or a list."
        )

    return raw


# ── Internal retry wrapper ────────────────────────────────────────────────────


async def _call_llm_with_retry(**kwargs: Any) -> Any:
    """Call ``litellm.acompletion`` with retry on ``RateLimitError``.

    Wraps the call in the module-level semaphore so at most
    ``MAX_CONCURRENT_LLM_REQUESTS`` calls are in-flight simultaneously.

    On ``RateLimitError`` the function sleeps for an exponentially-increasing
    delay then retries.  All other exceptions are re-raised immediately after
    the first failure.

    Parameters
    ----------
    **kwargs:
        Passed directly to ``litellm.acompletion``.  Must include ``model``.

    Returns
    -------
    Any
        The raw litellm response object.

    Raises
    ------
    LLMCallError
        After ``MAX_RETRY_ATTEMPTS`` failed attempts due to rate limiting, or
        immediately on any non-rate-limit exception.
    """
    semaphore = _get_semaphore()
    last_exc: Optional[Exception] = None

    # Extract model name for logging (it lives inside kwargs as a keyword arg).
    model_name: str = kwargs.get("model", "<unknown>")

    for attempt in range(MAX_RETRY_ATTEMPTS):
        if attempt > 0:
            delay = _backoff_delay(attempt - 1)
            logger.warning(
                "Rate limit on model %r (attempt %d/%d) — waiting %.1fs before retry.",
                model_name,
                attempt,
                MAX_RETRY_ATTEMPTS,
                delay,
            )
            await asyncio.sleep(delay)

        try:
            async with semaphore:
                return await litellm.acompletion(**kwargs)
        except litellm.RateLimitError as exc:
            last_exc = exc
            continue
        except Exception as exc:
            raise LLMCallError(
                f"LiteLLM call failed for model {model_name!r}: {exc}"
            ) from exc

    raise LLMCallError(
        f"Rate limit exceeded for model {model_name!r} after {MAX_RETRY_ATTEMPTS} attempt(s): "
        f"{last_exc}"
    ) from last_exc


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

    Automatically retries on ``RateLimitError`` (via ``_call_llm_with_retry``)
    and respects the global concurrency semaphore so parallel callers never
    burst past the provider's TPM ceiling simultaneously.

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
        On any network failure, non-200 status, or unexpected response shape,
        or after all retry attempts are exhausted for rate-limit errors.
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

    response = await _call_llm_with_retry(**kwargs)

    try:
        content: str = response.choices[0].message.content
        finish_reason: str = response.choices[0].finish_reason
    except (AttributeError, IndexError) as exc:
        raise LLMCallError(
            f"Unexpected LiteLLM response shape for model {config.model!r}: {exc}"
        ) from exc

    content = _normalise_json_content(content, config.model)

    return LLMResponse(
        content=content,
        raw_response=response,
        finish_reason=finish_reason,
    )


def validate_backend(backend: str) -> bool:
    """Return ``True`` if LiteLLM recognises *backend* as a valid provider string."""
    try:
        litellm.get_llm_provider(backend)
        return True
    except Exception:
        return False
