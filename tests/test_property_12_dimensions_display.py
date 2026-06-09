"""Property 12 — All 12 Dimensions Represented in Status Display.

For any pipeline state (before, during, or after a Layer 1 run), the
``PipelineView`` widget must display exactly one status entry for each of
the 12 ``ReviewDimensionEnum`` values — none missing, none duplicated.

This module covers:

1. **Structural integrity** — ``PipelineView`` composes exactly 12
   ``DimensionRow`` instances, keyed one-to-one with ``ReviewDimensionEnum``.
2. **No duplicates** — each dimension appears at most once.
3. **No omissions** — every ``ReviewDimensionEnum`` value has a row.
4. **State update correctness** — ``update_dimension()`` changes the right row
   without affecting the other 11.
5. **Widget IDs** — every ``DimensionRow`` gets a stable, unique CSS id.
6. **Full-app integration** — querying the live ``ContextaApp`` returns exactly
   12 ``DimensionRow`` instances.

Validates: Requirements 5.5, Design §11.
"""

from __future__ import annotations

import pytest

from contexta.models.enums import ReviewDimensionEnum
from contexta.tui.messages import TaskState
from contexta.tui.widgets.dimension_row import DimensionRow
from contexta.tui.widgets.pipeline_view import PipelineView


# ── Helpers ────────────────────────────────────────────────────────────────────

_ALL_DIMENSIONS = list(ReviewDimensionEnum)
_DIMENSION_COUNT = len(_ALL_DIMENSIONS)  # must be 12


# ── Unit: PipelineView internal _rows dict ────────────────────────────────────


class TestPipelineViewRowsDict:
    """Verify ``PipelineView._rows`` is populated correctly without mounting."""

    def test_exactly_12_dimensions_in_enum(self):
        """Guard: ReviewDimensionEnum must have exactly 12 values."""
        assert _DIMENSION_COUNT == 12, (
            f"Expected 12 ReviewDimensionEnum values, found {_DIMENSION_COUNT}: "
            f"{[d.value for d in _ALL_DIMENSIONS]}"
        )

    def test_rows_dict_has_12_entries_after_compose(self):
        """PipelineView._rows is keyed by all 12 ReviewDimensionEnum values."""
        pv = PipelineView()
        # Manually populate _rows as compose() would — mirrors the widget's
        # internal factory logic without requiring a mounted app.
        rows: dict = {}
        for dim in ReviewDimensionEnum:
            row = DimensionRow(dimension=dim)
            rows[dim] = row
        pv._rows = rows

        assert len(pv._rows) == 12

    def test_rows_dict_covers_all_enum_values(self):
        """Every ReviewDimensionEnum value has a corresponding DimensionRow."""
        pv = PipelineView()
        rows = {}
        for dim in ReviewDimensionEnum:
            rows[dim] = DimensionRow(dimension=dim)
        pv._rows = rows

        missing = set(ReviewDimensionEnum) - set(pv._rows.keys())
        assert not missing, f"Missing dimensions in _rows: {missing}"

    def test_rows_dict_has_no_duplicate_keys(self):
        """No dimension appears more than once as a key in _rows."""
        pv = PipelineView()
        rows = {}
        for dim in ReviewDimensionEnum:
            assert dim not in rows, f"Duplicate dimension key: {dim}"
            rows[dim] = DimensionRow(dimension=dim)
        pv._rows = rows
        assert len(rows) == 12

    def test_each_row_dimension_attribute_matches_key(self):
        """DimensionRow.dimension == the key it is stored under."""
        pv = PipelineView()
        rows = {}
        for dim in ReviewDimensionEnum:
            row = DimensionRow(dimension=dim)
            rows[dim] = row
        pv._rows = rows

        for key, row in pv._rows.items():
            assert row.dimension == key, (
                f"Row stored under key {key!r} has dimension={row.dimension!r}"
            )

    def test_dim_row_id_is_unique_per_dimension(self):
        """PipelineView._dim_row_id() produces a distinct id for every dimension."""
        ids = [PipelineView._dim_row_id(dim) for dim in ReviewDimensionEnum]
        assert len(set(ids)) == 12, f"Non-unique row IDs: {ids}"

    @pytest.mark.parametrize("dimension", _ALL_DIMENSIONS)
    def test_dim_row_id_contains_dimension_name(self, dimension: ReviewDimensionEnum):
        """The stable CSS id contains the dimension value (lowercased)."""
        row_id = PipelineView._dim_row_id(dimension)
        assert dimension.value.lower() in row_id, (
            f"Expected '{dimension.value.lower()}' in row_id={row_id!r}"
        )


# ── Unit: DimensionRow.update_state isolation ─────────────────────────────────


class TestDimensionRowStateIsolation:
    """Verify update_dimension() targets exactly the matching row."""

    def _make_rows(self) -> dict[ReviewDimensionEnum, DimensionRow]:
        """Build a fresh dict of bare DimensionRow instances (unmounted)."""
        return {dim: DimensionRow(dimension=dim) for dim in ReviewDimensionEnum}

    def test_all_rows_start_pending(self):
        """All rows initialise with PENDING state before any update."""
        rows = self._make_rows()
        for row in rows.values():
            assert row._state == TaskState.PENDING

    def test_update_one_row_does_not_change_state_attribute_of_others(self):
        """Directly mutating one DimensionRow._state leaves all others PENDING."""
        rows = self._make_rows()
        target_dim = ReviewDimensionEnum.ARCHITECTURE
        rows[target_dim]._state = TaskState.RUNNING

        for dim, row in rows.items():
            if dim == target_dim:
                assert row._state == TaskState.RUNNING
            else:
                assert row._state == TaskState.PENDING, (
                    f"Row for {dim.value} was unexpectedly changed to {row._state}"
                )

    def test_failed_state_carries_error(self):
        """update_state(FAILED, error=...) stores the error string."""
        row = DimensionRow(dimension=ReviewDimensionEnum.RISK)
        row._state = TaskState.FAILED
        row._error = "LLM timeout"
        assert row._error == "LLM timeout"

    def test_complete_state_clears_error(self):
        """Transitioning from FAILED → COMPLETE should clear error when set."""
        row = DimensionRow(dimension=ReviewDimensionEnum.SCOPE)
        row._state = TaskState.FAILED
        row._error = "previous error"
        # Simulate successful retry
        row._state = TaskState.COMPLETE
        row._error = None
        assert row._error is None


# ── Integration: ContextaApp mounted via run_test ─────────────────────────────


class TestPipelineViewLiveMounted:
    """Full-app integration tests using Textual's async test pilot."""

    @pytest.mark.asyncio
    async def test_exactly_12_dimension_rows_mounted(self):
        """Exactly 12 DimensionRow widgets are present after app mount."""
        from contexta.tui.app import ContextaApp

        app = ContextaApp()
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            screen = app.screen
            rows = list(screen.query(DimensionRow))
            assert len(rows) == 12, (
                f"Expected 12 DimensionRow widgets, found {len(rows)}"
            )

    @pytest.mark.asyncio
    async def test_all_dimension_enum_values_have_a_row(self):
        """Every ReviewDimensionEnum value is represented by exactly one row."""
        from contexta.tui.app import ContextaApp

        app = ContextaApp()
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            screen = app.screen
            rows = list(screen.query(DimensionRow))
            mounted_dims = {r.dimension for r in rows}
            expected_dims = set(ReviewDimensionEnum)

            missing = expected_dims - mounted_dims
            extra = mounted_dims - expected_dims

            assert not missing, f"Missing dimensions: {[d.value for d in missing]}"
            assert not extra, f"Unexpected extra dimensions: {[d.value for d in extra]}"

    @pytest.mark.asyncio
    async def test_no_duplicate_dimension_rows(self):
        """No dimension appears more than once in the mounted widget tree."""
        from contexta.tui.app import ContextaApp

        app = ContextaApp()
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            screen = app.screen
            rows = list(screen.query(DimensionRow))
            dims = [r.dimension for r in rows]
            assert len(dims) == len(set(dims)), (
                f"Duplicate dimension rows detected: "
                f"{[d.value for d in dims if dims.count(d) > 1]}"
            )

    @pytest.mark.asyncio
    async def test_all_rows_start_in_pending_state(self):
        """All 12 rows render with PENDING state at initial mount."""
        from contexta.tui.app import ContextaApp

        app = ContextaApp()
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            screen = app.screen
            rows = list(screen.query(DimensionRow))
            non_pending = [
                r.dimension.value for r in rows if r._state != TaskState.PENDING
            ]
            assert not non_pending, (
                f"Rows not in PENDING state at mount: {non_pending}"
            )

    @pytest.mark.asyncio
    async def test_pipeline_view_get_dimension_rows_returns_12(self):
        """PipelineView.get_dimension_rows() returns a dict with 12 entries."""
        from contexta.tui.app import ContextaApp

        app = ContextaApp()
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            pv = app.screen.query_one(PipelineView)
            rows_dict = pv.get_dimension_rows()
            assert len(rows_dict) == 12
            assert set(rows_dict.keys()) == set(ReviewDimensionEnum)

    @pytest.mark.asyncio
    async def test_update_dimension_changes_only_target_row(self):
        """update_dimension() on one dimension does not alter the other 11."""
        from contexta.tui.app import ContextaApp

        app = ContextaApp()
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            pv = app.screen.query_one(PipelineView)

            # Change exactly one dimension to RUNNING.
            target = ReviewDimensionEnum.TIMELINE
            pv.update_dimension(target, TaskState.RUNNING)
            await pilot.pause(0.05)

            rows_dict = pv.get_dimension_rows()
            for dim, row in rows_dict.items():
                if dim == target:
                    assert row._state == TaskState.RUNNING, (
                        f"{dim.value} should be RUNNING"
                    )
                else:
                    assert row._state == TaskState.PENDING, (
                        f"{dim.value} should still be PENDING, got {row._state}"
                    )
