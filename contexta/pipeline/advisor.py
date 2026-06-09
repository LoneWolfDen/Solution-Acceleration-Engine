"""Pipeline — Proactive Advisor (high-risk tag pattern detection).

Design contracts
----------------
- ``ProactiveAdvisor.evaluate()`` queries ``get_insights_for_tags()`` from
  the DB repositories layer and returns strict ``AdvisoryAlert`` objects.
- A match occurs when ``InsightRow.client_or_industry_tag`` is present in
  the supplied ``global_tags`` list.  Non-matching rows are silently
  discarded — no partial alerts are returned.
- The function is async because ``get_insights_for_tags()`` requires an
  ``aiosqlite.Connection``.
- ``AdvisoryAlert`` is a plain dataclass — it is never written to the DB
  and carries no Pydantic dependency.
- Property 16 (Proactive Advisor Tag Matching) asserts that for any set of
  ``global_tags`` and ``InsightRow`` collections, ``evaluate()`` returns
  alerts for all matching tags and zero alerts for non-matching tags.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..db.repositories import get_insights_for_tags


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class AdvisoryAlert:
    """A single high-risk advisory raised by the ``ProactiveAdvisor``.

    Attributes
    ----------
    tag_combination:
        The project tag(s) that triggered this alert.  Contains at least
        one element — the matching ``client_or_industry_tag`` value.
    pattern:
        The ``observed_pattern`` string from the ``global_client_insights``
        row that matched.
    frequency_count:
        How many times this ``(tag, pattern)`` combination has been
        observed across historical projects.
    """

    tag_combination: List[str] = field(default_factory=list)
    pattern: str = ""
    frequency_count: int = 0


# ── Advisor ───────────────────────────────────────────────────────────────────


class ProactiveAdvisor:
    """Queries the global client insights table for high-risk tag patterns.

    Usage
    -----
    Instantiate once (stateless) and call ``evaluate()`` before each
    Layer 2 synthesis run.  The TUI coordinator handles the returned
    ``AdvisoryAlert`` list by opening a ``RiskBlockingModal`` if non-empty.
    """

    async def evaluate(
        self,
        global_tags: List[str],
        conn: object,  # aiosqlite.Connection — typed as object to avoid circular import
    ) -> List[AdvisoryAlert]:
        """Query insights and return alerts for all matching project tags.

        Parameters
        ----------
        global_tags:
            The current project's global tag list (e.g.
            ``["#Lean-Client-Team", "#FinServ"]``).
        conn:
            Active ``aiosqlite.Connection``.

        Returns
        -------
        List[AdvisoryAlert]
            One ``AdvisoryAlert`` per ``(tag, pattern)`` pair where the
            ``client_or_industry_tag`` appears in ``global_tags``.  Empty
            list when no matches exist.
        """
        insights = await get_insights_for_tags(conn, global_tags)

        alerts: List[AdvisoryAlert] = []
        for insight in insights:
            if insight.client_or_industry_tag in global_tags:
                alerts.append(
                    AdvisoryAlert(
                        tag_combination=[insight.client_or_industry_tag],
                        pattern=insight.observed_pattern,
                        frequency_count=insight.frequency_count,
                    )
                )
        return alerts
