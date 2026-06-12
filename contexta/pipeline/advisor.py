"""Proactive Advisor — high-risk tag pattern detection.

The ``ProactiveAdvisor`` evaluates the active project's ``global_tags`` against
known patterns stored in ``global_client_insights`` and returns blocking
``AdvisoryAlert`` objects for any matches.

Design contracts
----------------
- ``evaluate()`` returns an alert for every matching ``(client_tag, pattern)``
  pair where ``client_tag`` is a member of *global_tags* (Property 16).
- No alerts are returned for tags not present in *global_tags*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import aiosqlite

from ..db.repositories import get_insights_for_tags


# ── Alert ─────────────────────────────────────────────────────────────────────


@dataclass
class AdvisoryAlert:
    """Represents a single high-risk pattern match."""

    tag_combination: List[str]
    pattern: str
    frequency_count: int


# ── Advisor ───────────────────────────────────────────────────────────────────


class ProactiveAdvisor:
    """Evaluates global tags against the insights table."""

    async def evaluate(
        self,
        global_tags: List[str],
        conn: aiosqlite.Connection,
    ) -> List[AdvisoryAlert]:
        """Return advisory alerts for all matching tag/pattern pairs.

        Parameters
        ----------
        global_tags:
            The active project's tag list.
        conn:
            Open database connection.

        Returns
        -------
        List[AdvisoryAlert]
            One alert per matching ``(client_or_industry_tag, observed_pattern)``
            row.  Empty list if no matches.
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
