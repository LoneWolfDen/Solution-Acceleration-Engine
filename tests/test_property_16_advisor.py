"""Property 16 — Proactive Advisor Tag Matching.

For any set of ``global_tags`` and any collection of ``InsightRow`` objects,
``ProactiveAdvisor.evaluate()`` must return:
- Exactly one ``AdvisoryAlert`` per ``InsightRow`` whose
  ``client_or_industry_tag`` appears in ``global_tags``.
- Zero alerts for rows whose tag is not in ``global_tags``.

The ``get_insights_for_tags`` DB call is always mocked — no live DB needed.

Coverage
--------
- Unit: matching single tag returns one alert.
- Unit: non-matching tag returns empty list.
- Unit: multiple tags — only matching ones produce alerts.
- Unit: duplicate insight rows produce duplicate alerts.
- Unit: empty global_tags returns empty list.
- Unit: empty insights DB returns empty list.
- Unit: AdvisoryAlert fields map correctly from InsightRow.
- Hypothesis: Property 16 — arbitrary tags/insights, assert exact match set.
"""

from __future__ import annotations

import asyncio
from typing import List
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from contexta.db.models import InsightRow
from contexta.pipeline.advisor import AdvisoryAlert, ProactiveAdvisor


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_insight(tag: str, pattern: str, freq: int = 1) -> InsightRow:
    return InsightRow(
        id=f"ins-{tag}-{pattern}",
        client_or_industry_tag=tag,
        observed_pattern=pattern,
        frequency_count=freq,
        last_updated="2025-01-01T00:00:00+00:00",
    )


async def _evaluate_with_mock_insights(
    global_tags: List[str],
    insights: List[InsightRow],
) -> List[AdvisoryAlert]:
    """Run evaluate() with insights injected via mock."""
    advisor = ProactiveAdvisor()
    mock_fn = AsyncMock(return_value=insights)
    with patch(
        "contexta.pipeline.advisor.get_insights_for_tags",
        mock_fn,
    ):
        return await advisor.evaluate(global_tags=global_tags, conn=object())


# ── Unit tests ────────────────────────────────────────────────────────────────


class TestProactiveAdvisorTagMatching:

    @pytest.mark.asyncio
    async def test_matching_tag_returns_alert(self):
        """Single matching tag produces exactly one AdvisoryAlert."""
        insights = [_make_insight("#FinServ", "HIGH_RISK_DELIVERY", freq=3)]
        alerts = await _evaluate_with_mock_insights(
            global_tags=["#FinServ"],
            insights=insights,
        )
        assert len(alerts) == 1
        assert alerts[0].pattern == "HIGH_RISK_DELIVERY"
        assert alerts[0].frequency_count == 3
        assert "#FinServ" in alerts[0].tag_combination

    @pytest.mark.asyncio
    async def test_non_matching_tag_returns_no_alerts(self):
        """Tag in InsightRow that is not in global_tags → no alert."""
        insights = [_make_insight("#FinServ", "HIGH_RISK_DELIVERY")]
        alerts = await _evaluate_with_mock_insights(
            global_tags=["#HealthTech"],
            insights=insights,
        )
        assert alerts == []

    @pytest.mark.asyncio
    async def test_multiple_insights_partial_match(self):
        """Only matching tags produce alerts; non-matching are discarded."""
        insights = [
            _make_insight("#FinServ", "HIGH_RISK_DELIVERY"),
            _make_insight("#GovSector", "HIGH_RISK_TIMELINE"),
            _make_insight("#HealthTech", "HIGH_RISK_RESOURCE"),
        ]
        alerts = await _evaluate_with_mock_insights(
            global_tags=["#FinServ", "#HealthTech"],
            insights=insights,
        )
        assert len(alerts) == 2
        patterns = {a.pattern for a in alerts}
        assert patterns == {"HIGH_RISK_DELIVERY", "HIGH_RISK_RESOURCE"}

    @pytest.mark.asyncio
    async def test_empty_global_tags_returns_no_alerts(self):
        """Empty tag list never matches anything."""
        insights = [_make_insight("#FinServ", "PATTERN")]
        alerts = await _evaluate_with_mock_insights(
            global_tags=[],
            insights=insights,
        )
        assert alerts == []

    @pytest.mark.asyncio
    async def test_empty_insights_returns_no_alerts(self):
        """No insights in DB → no alerts regardless of tags."""
        alerts = await _evaluate_with_mock_insights(
            global_tags=["#FinServ"],
            insights=[],
        )
        assert alerts == []

    @pytest.mark.asyncio
    async def test_alert_fields_map_correctly(self):
        """AdvisoryAlert fields match the source InsightRow exactly."""
        insight = _make_insight("#LeanTeam", "HIGH_RISK_OWNERSHIP", freq=7)
        alerts = await _evaluate_with_mock_insights(
            global_tags=["#LeanTeam"],
            insights=[insight],
        )
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.tag_combination == ["#LeanTeam"]
        assert alert.pattern == "HIGH_RISK_OWNERSHIP"
        assert alert.frequency_count == 7

    @pytest.mark.asyncio
    async def test_multiple_patterns_same_tag(self):
        """Multiple insight rows with the same tag produce multiple alerts."""
        insights = [
            _make_insight("#FinServ", "HIGH_RISK_DELIVERY"),
            _make_insight("#FinServ", "HIGH_RISK_TIMELINE"),
            _make_insight("#FinServ", "HIGH_RISK_NFR"),
        ]
        alerts = await _evaluate_with_mock_insights(
            global_tags=["#FinServ"],
            insights=insights,
        )
        assert len(alerts) == 3

    @pytest.mark.asyncio
    async def test_all_tags_matching_returns_all_alerts(self):
        """When all insight tags match, all rows produce alerts."""
        insights = [
            _make_insight("#T1", "P1"),
            _make_insight("#T2", "P2"),
            _make_insight("#T3", "P3"),
        ]
        alerts = await _evaluate_with_mock_insights(
            global_tags=["#T1", "#T2", "#T3"],
            insights=insights,
        )
        assert len(alerts) == 3

    @pytest.mark.asyncio
    async def test_get_insights_called_with_correct_tags(self):
        """get_insights_for_tags is called with the provided global_tags."""
        advisor = ProactiveAdvisor()
        mock_fn = AsyncMock(return_value=[])
        tags = ["#Alpha", "#Beta"]
        conn = object()
        with patch("contexta.pipeline.advisor.get_insights_for_tags", mock_fn):
            await advisor.evaluate(global_tags=tags, conn=conn)
        mock_fn.assert_called_once_with(conn, tags)

    @pytest.mark.asyncio
    async def test_return_type_is_list_of_advisory_alerts(self):
        """evaluate() always returns a list of AdvisoryAlert objects."""
        insights = [_make_insight("#X", "PATTERN", freq=2)]
        alerts = await _evaluate_with_mock_insights(
            global_tags=["#X"],
            insights=insights,
        )
        assert isinstance(alerts, list)
        assert all(isinstance(a, AdvisoryAlert) for a in alerts)

    @pytest.mark.asyncio
    async def test_insights_not_in_tags_filtered_even_when_returned_by_db(self):
        """DB may return rows that don't match; those are filtered out."""
        # Simulate a DB returning rows for unrelated tags alongside matching ones
        insights = [
            _make_insight("#Match", "MATCH_PATTERN"),
            _make_insight("#NoMatch", "SKIP_PATTERN"),
        ]
        alerts = await _evaluate_with_mock_insights(
            global_tags=["#Match"],
            insights=insights,
        )
        assert len(alerts) == 1
        assert alerts[0].pattern == "MATCH_PATTERN"


# ── Hypothesis: Property 16 ───────────────────────────────────────────────────


_tag_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz#_-",
    min_size=1,
    max_size=20,
)

_insight_strategy = st.builds(
    _make_insight,
    tag=_tag_strategy,
    pattern=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_", min_size=1, max_size=30),
    freq=st.integers(min_value=1, max_value=100),
)


@given(
    global_tags=st.lists(_tag_strategy, min_size=0, max_size=10),
    insights=st.lists(_insight_strategy, min_size=0, max_size=20),
)
@settings(max_examples=200)
def test_property_16_advisor_tag_matching(
    global_tags: List[str],
    insights: List[InsightRow],
) -> None:
    """Property 16: evaluate() returns alerts iff tag matches, zero otherwise.

    For any combination of global_tags and InsightRow list:
    - Every returned alert has tag_combination[0] in global_tags.
    - Every InsightRow with a matching tag produces exactly one alert.
    - InsightRows without a matching tag produce no alert.
    """
    async def _run() -> None:
        alerts = await _evaluate_with_mock_insights(global_tags, insights)

        # Every alert's tag must be in global_tags
        for alert in alerts:
            assert alert.tag_combination[0] in global_tags, (
                f"Alert tag {alert.tag_combination[0]!r} not in global_tags={global_tags!r}"
            )

        # Count expected alerts (insights whose tag is in global_tags)
        expected_count = sum(
            1 for ins in insights if ins.client_or_industry_tag in global_tags
        )
        assert len(alerts) == expected_count, (
            f"Expected {expected_count} alerts, got {len(alerts)}. "
            f"global_tags={global_tags!r}"
        )

    asyncio.run(_run())
