"""contexta/services/arbitration.py — Arbitration orchestration service.

Sits between the TUI and the pipeline layer.  Owns three responsibilities:

1. **DB fetch** — retrieves the active blueprint via the repository layer.
2. **Token guard** — estimates the full prompt token count before any LLM call
   and enforces the Groq 12,000 TPM ceiling, raising ``TokenLimitError`` if
   the request would exceed it.
3. **Engine delegation** — builds ``PromptBuilder`` + ``ArbitratorEngine``,
   invokes ``engine.run()``, and translates all exceptions into
   ``ArbitrationStatus`` transitions via the caller-supplied callback.

TUI integration
---------------
Pass an ``on_status_change`` coroutine to ``ArbitrationService.__init__()``.
It will be awaited on every status transition, giving the TUI a clean hook to
update labels and spinners without coupling itself to pipeline internals::

    async def handle_status(status: ArbitrationStatus, detail: str | None) -> None:
        app.post_message(ArbitrationStatusChanged(status, detail))

    service = ArbitrationService(config, conn, on_status_change=handle_status)
    result  = await service.run(payloads)

Error surface
-------------
- ``TokenLimitError``  — pre-flight check failed; request not sent.
- ``ArbitratorError``  — LLM call failed or response could not be parsed.
- ``LLMCallError``     — propagated if the LLM transport layer raises directly.
- ``RuntimeError``     — no active blueprint in the database.

All exceptions are re-raised after the appropriate status callback fires, so
the TUI can handle them at the call site if needed.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Callable, Awaitable, List, Optional

import aiosqlite

from ..config import ContextaConfig
from ..db.repositories import get_active_blueprint
from ..llm.prompts import PromptBuilder
from ..llm.provider import LLMCallError
from ..models.payloads import ReviewNodePayload
from ..pipeline.arbitrator import ArbitratorEngine, ArbitratorError, ArbitratorResult

logger = logging.getLogger(__name__)

# ── Groq TPM ceiling ──────────────────────────────────────────────────────────

#: Default token-per-minute limit enforced by the pre-flight guard.
#: Matches Groq's free-tier TPM ceiling as of 2024.
GROQ_TPM_LIMIT: int = 12_000

#: Characters-per-token estimate used by the heuristic counter.
#: 4 chars ≈ 1 token is a well-established conservative approximation.
_CHARS_PER_TOKEN: int = 4


# ── Public types ──────────────────────────────────────────────────────────────


class ArbitrationStatus(str, Enum):
    """Status values emitted via ``on_status_change`` during a run."""

    PENDING = "Pending"
    PROCESSING = "Processing..."
    RATE_LIMITED = "Rate Limited"
    COMPLETE = "Complete"
    FAILED = "Failed"


class TokenLimitError(Exception):
    """Raised when the pre-flight token estimate exceeds the TPM limit.

    The LLM call is **not** made when this is raised.
    """


#: Type alias for the async status callback accepted by ``ArbitrationService``.
StatusCallback = Callable[[ArbitrationStatus, Optional[str]], Awaitable[None]]


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _noop_callback(status: ArbitrationStatus, detail: Optional[str]) -> None:  # noqa: ARG001
    """Default no-op status callback used when the caller supplies none."""


def _is_rate_limit_signal(message: str) -> bool:
    """Return True if *message* contains recognisable rate-limit indicators."""
    lower = message.lower()
    return "rate" in lower or "429" in lower or "tpm" in lower or "ratelimit" in lower


def estimate_token_count(texts: List[str]) -> int:
    """Estimate total token count for a list of text strings.

    Uses the 4-chars-per-token heuristic, which is conservative enough for a
    Groq TPM pre-flight check.  Accuracy is intentionally traded for
    zero-dependency simplicity — no tokeniser library is required.

    Parameters
    ----------
    texts:
        Strings to measure; typically ``[system_prompt, user_prompt]``.

    Returns
    -------
    int
        Estimated token count (always >= 0).
    """
    return sum(len(t) for t in texts) // _CHARS_PER_TOKEN


# ── Service ───────────────────────────────────────────────────────────────────


class ArbitrationService:
    """Orchestrates the full Layer 2 arbitration pipeline.

    Parameters
    ----------
    config:
        Application configuration.  ``config.as_llm_config()`` is called
        at run time to produce the ``LLMConfig`` passed to the engine.
    conn:
        Open ``aiosqlite`` connection used for all DB queries.
    on_status_change:
        Async callback invoked on each ``ArbitrationStatus`` transition.
        Receives ``(status, detail)`` where *detail* is ``None`` on
        non-error transitions and an error message string on failures.
        Defaults to a no-op if omitted.
    tpm_limit:
        Token-per-minute ceiling enforced by the pre-flight guard.
        Defaults to ``GROQ_TPM_LIMIT`` (12,000).
    """

    def __init__(
        self,
        config: ContextaConfig,
        conn: aiosqlite.Connection,
        on_status_change: StatusCallback = _noop_callback,
        tpm_limit: int = GROQ_TPM_LIMIT,
    ) -> None:
        self._config = config
        self._conn = conn
        self._on_status_change = on_status_change
        self._tpm_limit = tpm_limit

    async def run(self, payloads: List[ReviewNodePayload]) -> ArbitratorResult:
        """Execute the full arbitration pipeline.

        Steps
        -----
        1. Emit ``PROCESSING`` status.
        2. Fetch the active blueprint from the DB.
        3. Serialise *payloads* and build the arbitrator prompt strings.
        4. Estimate token count; raise ``TokenLimitError`` (+ ``RATE_LIMITED``
           status) if the estimate exceeds ``tpm_limit``.
        5. Instantiate ``ArbitratorEngine`` and call ``engine.run()``.
        6. Emit ``COMPLETE`` on success, or the appropriate failure status on
           any exception before re-raising.

        Parameters
        ----------
        payloads:
            Exactly 12 validated ``ReviewNodePayload`` objects — one per
            ``ReviewDimensionEnum`` value.  The ``ArbitratorEngine`` enforces
            this contract; the service does not duplicate the check.

        Returns
        -------
        ArbitratorResult

        Raises
        ------
        TokenLimitError
            Pre-flight check failed; LLM call was not made.
        ArbitratorError
            LLM call failed or response parsing failed.
        LLMCallError
            Propagated if the transport layer raises outside the engine.
        RuntimeError
            No active blueprint found in the database.
        """
        await self._on_status_change(ArbitrationStatus.PROCESSING, None)

        try:
            # ── 1. Blueprint ──────────────────────────────────────────────────
            blueprint = await get_active_blueprint(self._conn)
            if blueprint is None:
                raise RuntimeError(
                    "No active blueprint found. "
                    "Activate a blueprint before running arbitration."
                )

            # ── 2. Build prompts for token estimation ─────────────────────────
            serialised = [p.model_dump_json() for p in payloads]
            builder = PromptBuilder(blueprint=blueprint, schema_json="{}")
            system, user = builder.build_arbitrator_prompt(serialised)

            # ── 3. Pre-flight token count check ───────────────────────────────
            estimated = estimate_token_count([system, user])
            logger.debug(
                "Arbitration token pre-flight: estimated=%d limit=%d",
                estimated,
                self._tpm_limit,
            )
            if estimated > self._tpm_limit:
                detail = (
                    f"Pre-flight token check: estimated {estimated:,} tokens "
                    f"exceeds the {self._tpm_limit:,} TPM limit. "
                    "Reduce payload size or increase the limit."
                )
                await self._on_status_change(ArbitrationStatus.RATE_LIMITED, detail)
                raise TokenLimitError(detail)

            # ── 4. Run engine ─────────────────────────────────────────────────
            engine = ArbitratorEngine(self._config.as_llm_config(), builder)
            result = await engine.run(payloads)

            await self._on_status_change(ArbitrationStatus.COMPLETE, None)
            return result

        except TokenLimitError:
            # Already emitted RATE_LIMITED above — just propagate.
            raise

        except ArbitratorError as exc:
            detail = str(exc)
            status = (
                ArbitrationStatus.RATE_LIMITED
                if _is_rate_limit_signal(detail)
                else ArbitrationStatus.FAILED
            )
            await self._on_status_change(status, detail)
            raise

        except LLMCallError as exc:
            detail = str(exc)
            status = (
                ArbitrationStatus.RATE_LIMITED
                if _is_rate_limit_signal(detail)
                else ArbitrationStatus.FAILED
            )
            await self._on_status_change(status, detail)
            raise

        except Exception as exc:
            await self._on_status_change(ArbitrationStatus.FAILED, str(exc))
            raise
