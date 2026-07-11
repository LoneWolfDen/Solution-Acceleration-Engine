"""
contexta/api/routers/insights.py

GET /api/insights — return top advisory hints from global_client_insights.

Gap 10 — Requirements 10.1–10.3:
  - Returns up to 10 entries ordered by frequency_count DESC.
  - Returns an empty list (HTTP 200) when the table has no rows.
  - Each entry includes client_or_industry_tag, observed_pattern,
    frequency_count, and last_updated.
"""

from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, Depends

from contexta.api import schemas
from contexta.api.dependencies import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["insights"])


@router.get("/insights", response_model=schemas.InsightsResponse)
async def list_insights(
    conn: aiosqlite.Connection = Depends(get_db),
) -> schemas.InsightsResponse:
    """Return the top 10 advisory hints ordered by frequency_count descending.

    Gap 10 — Requirements 10.1/10.2/10.3/Property 16:
    - At most 10 entries are returned regardless of table size.
    - Ordering is frequency_count DESC so the highest-recurrence patterns
      appear first.
    - Returns an empty list with HTTP 200 when no insights exist.
    """
    cursor = await conn.execute(
        """
        SELECT id, client_or_industry_tag, observed_pattern,
               frequency_count, last_updated
        FROM global_client_insights
        ORDER BY frequency_count DESC
        LIMIT 10
        """
    )
    rows = await cursor.fetchall()

    return schemas.InsightsResponse(
        insights=[
            schemas.InsightItem(
                id=row["id"],
                client_or_industry_tag=row["client_or_industry_tag"],
                observed_pattern=row["observed_pattern"],
                frequency_count=row["frequency_count"],
                last_updated=row["last_updated"],
            )
            for row in rows
        ]
    )
