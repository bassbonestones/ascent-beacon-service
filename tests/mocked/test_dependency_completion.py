"""
Tests for dependency service and completion integration (Phase 4i-2).

Tests the dependency_service functions and the integration of dependency
checking into the complete, skip, and reopen endpoints.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.core.time import utc_now
from app.schemas.dependency import (
    DependencyBlocker,
    DependencyDependent,
    DependencyStatusResponse,
    TaskInfo,
)


# ===========================================================================
# Pure Function Tests - DependencyStatusResponse
# ===========================================================================


class TestWithinWindowAnchorEnd:
    """within_window_anchor_end caps occurrence time with wall-clock now."""

    def test_future_occurrence_uses_now(self) -> None:
        from app.services.dependency_service import within_window_anchor_end

        future = datetime(2030, 6, 1, 23, 0, 0, tzinfo=timezone.utc)
        now = datetime(2030, 6, 1, 15, 0, 0, tzinfo=timezone.utc)
        with patch("app.services.dependency_service.utc_now", return_value=now):
            assert within_window_anchor_end(future) == now

    def test_past_occurrence_uses_occurrence(self) -> None:
        from app.services.dependency_service import within_window_anchor_end

        past = datetime(2030, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        now = datetime(2030, 6, 1, 18, 0, 0, tzinfo=timezone.utc)
        with patch("app.services.dependency_service.utc_now", return_value=now):
            assert within_window_anchor_end(past) == past

    def test_naive_scheduled_assumes_utc(self) -> None:
        from app.services.dependency_service import within_window_anchor_end

        naive_noon = datetime(2030, 6, 1, 12, 0, 0)
        now = datetime(2030, 6, 1, 18, 0, 0, tzinfo=timezone.utc)
        with patch("app.services.dependency_service.utc_now", return_value=now):
            assert within_window_anchor_end(naive_noon) == datetime(
                2030, 6, 1, 12, 0, 0, tzinfo=timezone.utc
            )


class TestDependencyStatusComputation:
    """Test DependencyStatusResponse state computation."""
    
    def test_all_met_when_no_blockers(self) -> None:
        """Empty dependencies means all_met=True."""
        response = DependencyStatusResponse(
            task_id="task-1",
            scheduled_for=utc_now(),
            dependencies=[],
        )
        assert response.all_met is True
        assert response.has_unmet_hard is False
        assert response.has_unmet_soft is False
        assert response.readiness_state == "ready"
    
    def test_all_met_when_all_hard_met(self) -> None:
        """All hard deps met means all_met=True."""
        task_info = TaskInfo(id="t1", title="Task 1", is_recurring=False)
        response = DependencyStatusResponse(
            task_id="task-1",
            scheduled_for=utc_now(),
            dependencies=[
                DependencyBlocker(
                    rule_id="r1",
                    upstream_task=task_info,
                    strength="hard",
                    scope="next_occurrence",
                    required_count=1,
                    completed_count=1,
                    is_met=True,
                )
            ],
        )
        assert response.all_met is True
        assert response.has_unmet_hard is False
        assert response.readiness_state == "ready"
    
    def test_blocked_when_hard_unmet(self) -> None:
        """Unmet hard dep means blocked state."""
        task_info = TaskInfo(id="t1", title="Task 1", is_recurring=False)
        response = DependencyStatusResponse(
            task_id="task-1",
            scheduled_for=utc_now(),
            dependencies=[
                DependencyBlocker(
                    rule_id="r1",
                    upstream_task=task_info,
                    strength="hard",
                    scope="next_occurrence",
                    required_count=1,
                    completed_count=0,
                    is_met=False,
                )
            ],
        )
        assert response.all_met is False
        assert response.has_unmet_hard is True
        assert response.readiness_state == "blocked"
    
    def test_partial_when_some_hard_met(self) -> None:
        """Some hard met, some not means partial state."""
        task1 = TaskInfo(id="t1", title="Task 1", is_recurring=False)
        task2 = TaskInfo(id="t2", title="Task 2", is_recurring=False)
        response = DependencyStatusResponse(
            task_id="task-1",
            scheduled_for=utc_now(),
            dependencies=[
                DependencyBlocker(
                    rule_id="r1",
                    upstream_task=task1,
                    strength="hard",
                    scope="next_occurrence",
                    required_count=1,
                    completed_count=1,
                    is_met=True,
                ),
                DependencyBlocker(
                    rule_id="r2",
                    upstream_task=task2,
                    strength="hard",
                    scope="next_occurrence",
                    required_count=1,
                    completed_count=0,
                    is_met=False,
                ),
            ],
        )
        assert response.all_met is False
        assert response.has_unmet_hard is True
        assert response.readiness_state == "partial"
    
    def test_advisory_when_only_soft_unmet(self) -> None:
        """Only soft unmet means advisory state."""
        task_info = TaskInfo(id="t1", title="Task 1", is_recurring=False)
        response = DependencyStatusResponse(
            task_id="task-1",
            scheduled_for=utc_now(),
            dependencies=[
                DependencyBlocker(
                    rule_id="r1",
                    upstream_task=task_info,
                    strength="soft",
                    scope="next_occurrence",
                    required_count=1,
                    completed_count=0,
                    is_met=False,
                )
            ],
        )
        assert response.all_met is False
        assert response.has_unmet_hard is False
        assert response.has_unmet_soft is True
        assert response.readiness_state == "advisory"
    
    def test_progress_pct_calculation(self) -> None:
        """Test progress_pct property."""
        task_info = TaskInfo(id="t1", title="Task", is_recurring=False)
        blocker = DependencyBlocker(
            rule_id="r1",
            upstream_task=task_info,
            strength="hard",
            scope="next_occurrence",
            required_count=4,
            completed_count=2,
            is_met=False,
        )
        assert blocker.progress_pct == 50
    
    def test_progress_pct_zero_required(self) -> None:
        """Test progress_pct when 0 required."""
        task_info = TaskInfo(id="t1", title="Task", is_recurring=False)
        blocker = DependencyBlocker(
            rule_id="r1",
            upstream_task=task_info,
            strength="hard",
            scope="next_occurrence",
            required_count=0,
            completed_count=0,
            is_met=True,
        )
        assert blocker.progress_pct == 100


# ===========================================================================
# Pure Function Tests - DependencyBlockedResponse
# ===========================================================================


class TestDependencyBlockedResponse:
    """Test DependencyBlockedResponse schema."""
    
    def test_blocked_response_structure(self) -> None:
        """Test blocked response has correct fields."""
        from app.schemas.dependency import DependencyBlockedResponse
        
        task_info = TaskInfo(id="t1", title="Prereq Task", is_recurring=False)
        blocker = DependencyBlocker(
            rule_id="r1",
            upstream_task=task_info,
            strength="hard",
            scope="next_occurrence",
            required_count=1,
            completed_count=0,
            is_met=False,
        )
        
        response = DependencyBlockedResponse(
            task_id="downstream-task",
            scheduled_for=utc_now(),
            blockers=[blocker],
        )
        
        assert response.task_id == "downstream-task"
        assert len(response.blockers) == 1
        assert response.can_override is True
        assert "override_confirm" in response.hint


# ===========================================================================
# Service Logic Tests (mocked DB)
# ===========================================================================


class TestDependencyServiceHelpers:
    """Test dependency service helper functions."""
    
    def test_max_chain_depth_constant(self) -> None:
        """MAX_CHAIN_DEPTH should be reasonable."""
        from app.services.dependency_service import MAX_CHAIN_DEPTH
        
        assert MAX_CHAIN_DEPTH >= 10
        assert MAX_CHAIN_DEPTH <= 100
    
    @pytest.mark.asyncio
    async def test_get_upstream_recurrence_interval_daily(self) -> None:
        """Test recurrence interval for daily task."""
        from app.services.dependency_service import get_upstream_recurrence_interval_minutes
        
        task = MagicMock()
        task.is_recurring = True
        task.recurrence_rule = "FREQ=DAILY;BYHOUR=9"
        
        result = await get_upstream_recurrence_interval_minutes(task)
        assert result == 1440  # 24 hours
    
    @pytest.mark.asyncio
    async def test_get_upstream_recurrence_interval_weekly(self) -> None:
        """Test recurrence interval for weekly task."""
        from app.services.dependency_service import get_upstream_recurrence_interval_minutes
        
        task = MagicMock()
        task.is_recurring = True
        task.recurrence_rule = "FREQ=WEEKLY;BYDAY=MO"
        
        result = await get_upstream_recurrence_interval_minutes(task)
        assert result == 10080  # 7 days
    
    @pytest.mark.asyncio
    async def test_get_upstream_recurrence_interval_monthly(self) -> None:
        """Test recurrence interval for monthly task."""
        from app.services.dependency_service import get_upstream_recurrence_interval_minutes
        
        task = MagicMock()
        task.is_recurring = True
        task.recurrence_rule = "FREQ=MONTHLY;BYMONTHDAY=1"
        
        result = await get_upstream_recurrence_interval_minutes(task)
        assert result == 43200  # 30 days
    
    @pytest.mark.asyncio
    async def test_get_upstream_recurrence_interval_yearly(self) -> None:
        """Test recurrence interval for yearly task."""
        from app.services.dependency_service import get_upstream_recurrence_interval_minutes
        
        task = MagicMock()
        task.is_recurring = True
        task.recurrence_rule = "FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=1"
        
        result = await get_upstream_recurrence_interval_minutes(task)
        assert result == 525600  # 365 days
    
    @pytest.mark.asyncio
    async def test_get_upstream_recurrence_interval_hourly(self) -> None:
        """Test recurrence interval for hourly task."""
        from app.services.dependency_service import get_upstream_recurrence_interval_minutes
        
        task = MagicMock()
        task.is_recurring = True
        task.recurrence_rule = "FREQ=HOURLY"
        
        result = await get_upstream_recurrence_interval_minutes(task)
        assert result == 60  # 1 hour
    
    @pytest.mark.asyncio
    async def test_get_upstream_recurrence_interval_unknown_freq(self) -> None:
        """Test recurrence interval for unknown frequency defaults to daily."""
        from app.services.dependency_service import get_upstream_recurrence_interval_minutes
        
        task = MagicMock()
        task.is_recurring = True
        task.recurrence_rule = "FREQ=MINUTELY"  # Not explicitly handled
        
        result = await get_upstream_recurrence_interval_minutes(task)
        assert result == 1440  # Default to daily
    
    @pytest.mark.asyncio
    async def test_get_upstream_recurrence_interval_non_recurring(self) -> None:
        """Test recurrence interval for non-recurring task."""
        from app.services.dependency_service import get_upstream_recurrence_interval_minutes
        
        task = MagicMock()
        task.is_recurring = False
        task.recurrence_rule = None
        
        result = await get_upstream_recurrence_interval_minutes(task)
        assert result == 1440  # Default 24 hours


class TestRecordResolutions:
    """Test record_resolutions function."""
    
    @pytest.mark.asyncio
    async def test_record_resolution_creates_records(self) -> None:
        """Test that resolution records are created."""
        from app.services.dependency_service import record_resolutions
        
        # Mock db session
        db = AsyncMock()
        db.add = MagicMock()
        
        task_info = TaskInfo(id="t1", title="Task", is_recurring=False)
        blocker = DependencyBlocker(
            rule_id="r1",
            upstream_task=task_info,
            strength="hard",
            scope="next_occurrence",
            required_count=1,
            completed_count=1,
            is_met=True,
        )
        
        resolutions = await record_resolutions(
            db=db,
            downstream_completion_id="comp-123",
            blockers=[blocker],
            upstream_completion_ids={"r1": ["up-comp-1"]},
            resolution_source="manual",
        )
        
        assert len(resolutions) == 1
        assert resolutions[0].dependency_rule_id == "r1"
        assert resolutions[0].downstream_completion_id == "comp-123"
        assert resolutions[0].upstream_completion_id == "up-comp-1"
        assert resolutions[0].resolution_source == "manual"
    
    @pytest.mark.asyncio
    async def test_record_resolution_override(self) -> None:
        """Test override resolution records override_reason."""
        from app.services.dependency_service import record_resolutions
        
        db = AsyncMock()
        db.add = MagicMock()
        
        task_info = TaskInfo(id="t1", title="Task", is_recurring=False)
        blocker = DependencyBlocker(
            rule_id="r1",
            upstream_task=task_info,
            strength="hard",
            scope="next_occurrence",
            required_count=1,
            completed_count=0,
            is_met=False,
        )
        
        resolutions = await record_resolutions(
            db=db,
            downstream_completion_id="comp-123",
            blockers=[blocker],
            upstream_completion_ids={},
            resolution_source="override",
            override_reason="Urgent deadline",
        )
        
        assert len(resolutions) == 1
        assert resolutions[0].resolution_source == "override"
        assert resolutions[0].override_reason == "Urgent deadline"


class TestCheckHardDependents:
    """Test check_hard_dependents function."""
    
    @pytest.mark.asyncio
    async def test_returns_downstream_tasks(self) -> None:
        """Test that hard dependents are returned."""
        from app.services.dependency_service import check_hard_dependents
        
        # This requires DB mocking - we'll test via integration tests
        pass


class TestCountQualifyingCompletions:
    """Test _count_qualifying_completions edge cases."""
    
    @pytest.mark.asyncio
    async def test_unknown_scope_returns_zero(self) -> None:
        """Unknown scope returns 0 completions."""
        from app.services.dependency_service import _count_qualifying_completions
        
        # Create mock rule with unknown scope
        mock_rule = MagicMock()
        mock_rule.scope = "unknown_scope"
        
        mock_db = AsyncMock()
        
        result = await _count_qualifying_completions(
            mock_db, mock_rule, None, completion_statuses=("completed",)
        )
        assert result == 0


class TestResolveRuleValidityWindowMinutes:
    """resolve_rule_validity_window_minutes matches stated resolution (no N>1 floor)."""

    @pytest.mark.asyncio
    async def test_explicit_minutes_multi_count_unchanged(self) -> None:
        from app.services.dependency_service import resolve_rule_validity_window_minutes

        class Rule:
            validity_window_minutes = 840
            required_occurrence_count = 4
            upstream_task_id = str(uuid4())

        mock_db = AsyncMock()
        out = await resolve_rule_validity_window_minutes(mock_db, Rule())  # type: ignore[arg-type]
        assert out == 840
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_explicit_minutes_single_count_unchanged(self) -> None:
        from app.services.dependency_service import resolve_rule_validity_window_minutes

        class Rule:
            validity_window_minutes = 840
            required_occurrence_count = 1
            upstream_task_id = str(uuid4())

        mock_db = AsyncMock()
        out = await resolve_rule_validity_window_minutes(mock_db, Rule())  # type: ignore[arg-type]
        assert out == 840

    @pytest.mark.asyncio
    async def test_null_validity_uses_upstream_recurrence(self) -> None:
        from app.services.dependency_service import resolve_rule_validity_window_minutes

        class Rule:
            validity_window_minutes = None
            required_occurrence_count = 2
            upstream_task_id = str(uuid4())

        mock_db = AsyncMock()
        task_result = MagicMock()
        ut = MagicMock()
        ut.is_recurring = True
        ut.recurrence_rule = "FREQ=DAILY"
        task_result.scalar_one_or_none.return_value = ut
        mock_db.execute.return_value = task_result

        out = await resolve_rule_validity_window_minutes(mock_db, Rule())  # type: ignore[arg-type]
        assert out == 1440

    @pytest.mark.asyncio
    async def test_null_validity_missing_upstream_defaults_1440(self) -> None:
        from app.services.dependency_service import resolve_rule_validity_window_minutes

        class Rule:
            validity_window_minutes = None
            required_occurrence_count = 2
            upstream_task_id = str(uuid4())

        mock_db = AsyncMock()
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = task_result

        out = await resolve_rule_validity_window_minutes(mock_db, Rule())  # type: ignore[arg-type]
        assert out == 1440


class TestResolveNextOccurrenceEarlyBreak:
    """Cover early exit when required_occurrence_count is met."""

    @pytest.mark.asyncio
    async def test_breaks_when_count_reached(self) -> None:
        from unittest.mock import patch

        from app.services.dependency_service import _resolve_next_occurrence

        anchor = datetime(2026, 6, 1, 15, 0, 0, tzinfo=timezone.utc)

        mock_rule = MagicMock()
        mock_rule.upstream_task_id = str(uuid4())
        mock_rule.required_occurrence_count = 2
        mock_rule.id = str(uuid4())

        c1, c2, c3 = MagicMock(), MagicMock(), MagicMock()
        c1.id = "a"
        c2.id = "b"
        c3.id = "c"
        for c in (c1, c2, c3):
            c.scheduled_for = anchor
            c.completed_at = anchor
            c.local_date = None

        comp_result = MagicMock()
        comp_result.scalars.return_value.all.return_value = [c1, c2, c3]

        ut = MagicMock()
        ut.is_recurring = True
        ut.recurrence_rule = "FREQ=DAILY"
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = ut

        cons_result = MagicMock()
        cons_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [task_result, comp_result, cons_result]

        with patch("app.services.dependency_service.utc_now", return_value=anchor):
            result = await _resolve_next_occurrence(
                mock_db, mock_rule, anchor, ("completed",),
            )
        assert result == 2

    @pytest.mark.asyncio
    async def test_upstream_task_missing_skips_period_filter(self) -> None:
        """No prerequisite row: Rule B filter skipped (branch ``upstream is None``)."""
        from app.services.dependency_service import _resolve_next_occurrence

        anchor = datetime(2026, 6, 1, 15, 0, 0, tzinfo=timezone.utc)
        other_day = datetime(2026, 6, 10, 15, 0, 0, tzinfo=timezone.utc)

        mock_rule = MagicMock()
        mock_rule.upstream_task_id = str(uuid4())
        mock_rule.required_occurrence_count = 1
        mock_rule.id = str(uuid4())

        c1 = MagicMock()
        c1.id = "a"
        c1.scheduled_for = other_day
        c1.completed_at = other_day
        c1.local_date = None

        comp_result = MagicMock()
        comp_result.scalars.return_value.all.return_value = [c1]

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None

        cons_result = MagicMock()
        cons_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [task_result, comp_result, cons_result]

        result = await _resolve_next_occurrence(
            mock_db, mock_rule, anchor, ("completed",),
        )
        assert result == 1


class TestResolveWithinWindow:
    """Test _resolve_within_window edge cases."""

    @pytest.mark.asyncio
    async def test_short_window_counts_completions_before_now_when_anchor_is_eod(
        self,
    ) -> None:
        """Far-future occurrence anchor caps with now so 'last 1 minute' is wall-clock."""
        from unittest.mock import patch

        from app.services.dependency_service import _resolve_within_window

        fixed_now = datetime(2026, 4, 12, 15, 0, 0, tzinfo=timezone.utc)
        eod = datetime(2026, 4, 12, 23, 59, 59, 999000, tzinfo=timezone.utc)

        mock_rule = MagicMock()
        mock_rule.validity_window_minutes = 1
        mock_rule.upstream_task_id = str(uuid4())
        mock_rule.id = str(uuid4())

        comp = MagicMock()
        comp.id = "c1"
        comp.completed_at = fixed_now - timedelta(seconds=5)

        completion_result = MagicMock()
        completion_result.scalars.return_value.all.return_value = [comp]
        consumed_result = MagicMock()
        consumed_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [completion_result, consumed_result]

        with patch("app.services.dependency_service.utc_now", return_value=fixed_now):
            with patch(
                "app.services.dependency_service.resolve_rule_validity_window_minutes",
                new_callable=AsyncMock,
                return_value=1,
            ):
                count = await _resolve_within_window(
                    mock_db, mock_rule, eod, completion_statuses=("completed",)
                )
        assert count == 1
    
    @pytest.mark.asyncio
    async def test_returns_zero_without_scheduled_for(self) -> None:
        """within_window returns 0 if no scheduled_for."""
        from app.services.dependency_service import _resolve_within_window
        
        mock_rule = MagicMock()
        mock_db = AsyncMock()
        
        result = await _resolve_within_window(
            mock_db, mock_rule, None, completion_statuses=("completed",)
        )
        assert result == 0


class TestGetTransitiveUnmetHardPrerequisites:
    """get_transitive_unmet_hard_prerequisites depth and visited short-circuit."""

    @pytest.mark.asyncio
    async def test_max_depth_raises(self) -> None:
        from app.services.dependency_service import (
            MAX_CHAIN_DEPTH,
            get_transitive_unmet_hard_prerequisites,
        )

        mock_db = AsyncMock()
        with pytest.raises(ValueError, match="exceeds maximum depth"):
            await get_transitive_unmet_hard_prerequisites(
                mock_db, "t1", "u1", None, depth=MAX_CHAIN_DEPTH
            )

    @pytest.mark.asyncio
    async def test_visited_task_returns_empty(self) -> None:
        from app.services.dependency_service import get_transitive_unmet_hard_prerequisites

        mock_db = AsyncMock()
        tid = str(uuid4())
        result = await get_transitive_unmet_hard_prerequisites(
            mock_db, tid, "u1", None, depth=0, visited={tid}
        )
        assert result == []
        mock_db.execute.assert_not_called()


class TestGetTransitiveBlockers:
    """Test get_transitive_blockers edge cases."""
    
    @pytest.mark.asyncio
    async def test_max_depth_exceeded_raises(self) -> None:
        """Exceeding max depth raises ValueError."""
        from app.services.dependency_service import get_transitive_blockers, MAX_CHAIN_DEPTH
        
        mock_db = AsyncMock()
        
        with pytest.raises(ValueError, match="exceeds maximum depth"):
            await get_transitive_blockers(
                mock_db, "task-1", "user-1", None, 
                depth=MAX_CHAIN_DEPTH  # At max depth
            )
    
    @pytest.mark.asyncio
    async def test_visited_task_returns_empty(self) -> None:
        """Already visited task returns empty list."""
        from app.services.dependency_service import get_transitive_blockers
        
        mock_db = AsyncMock()
        visited = {"task-1"}  # Task already visited
        
        result = await get_transitive_blockers(
            mock_db, "task-1", "user-1", None, 
            depth=0, visited=visited
        )
        assert result == []


class TestGetQualifyingUpstreamIds:
    """Test get_qualifying_upstream_ids for different scopes."""
    
    @pytest.mark.asyncio
    async def test_unknown_scope_returns_empty(self) -> None:
        """Unknown scope returns empty list."""
        from app.services.dependency_service import get_qualifying_upstream_ids
        
        mock_rule = MagicMock()
        mock_rule.scope = "unknown_scope"
        
        mock_db = AsyncMock()
        
        result = await get_qualifying_upstream_ids(mock_db, mock_rule, None, 1)
        assert result == []
    
    @pytest.mark.asyncio
    async def test_within_window_no_scheduled_for(self) -> None:
        """within_window scope with no downstream_scheduled_for sets window_start to None."""
        from app.services.dependency_service import get_qualifying_upstream_ids
        
        mock_rule = MagicMock()
        mock_rule.scope = "within_window"
        mock_rule.validity_window_minutes = 60
        mock_rule.upstream_task_id = str(uuid4())
        mock_rule.id = str(uuid4())
        
        # Mock db to return empty completions
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        # Call with no downstream_scheduled_for - hits line 443
        result = await get_qualifying_upstream_ids(mock_db, mock_rule, None, 1)
        assert result == []

    @pytest.mark.asyncio
    async def test_next_occurrence_upstream_missing_no_period_filter(self) -> None:
        """``next_occurrence`` with missing Task row skips period filter."""
        from app.services.dependency_service import get_qualifying_upstream_ids

        mock_rule = MagicMock()
        mock_rule.scope = "next_occurrence"
        mock_rule.strength = "soft"
        mock_rule.upstream_task_id = str(uuid4())
        mock_rule.id = str(uuid4())

        c1 = MagicMock()
        c1.id = "u1"

        comp_result = MagicMock()
        comp_result.scalars.return_value.all.return_value = [c1]

        cons_result = MagicMock()
        cons_result.scalars.return_value.all.return_value = []

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [task_result, comp_result, cons_result]

        anchor = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = await get_qualifying_upstream_ids(mock_db, mock_rule, anchor, 3)
        assert result == ["u1"]


@pytest.mark.asyncio
class TestResolveWithinWindowEdgeCases:
    """Test edge cases in _resolve_within_window."""
    
    async def test_upstream_task_not_found_uses_default(self) -> None:
        """When upstream task is not found, uses 1440 minute default window."""
        from app.services.dependency_service import _resolve_within_window
        
        mock_rule = MagicMock()
        mock_rule.validity_window_minutes = None  # Force task lookup
        mock_rule.upstream_task_id = str(uuid4())
        mock_rule.id = str(uuid4())
        
        # Mock db - first query returns None (task not found), second returns empty completions
        mock_db = AsyncMock()
        
        # Setup mock results for sequential calls
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = None  # Task not found - hits line 276
        
        completion_result = MagicMock()
        completion_result.scalars.return_value.all.return_value = []
        
        consumed_result = MagicMock()
        consumed_result.scalars.return_value.all.return_value = []
        
        mock_db.execute.side_effect = [task_result, completion_result, consumed_result]
        
        scheduled_for = datetime.now()
        
        result = await _resolve_within_window(
            mock_db, mock_rule, scheduled_for, completion_statuses=("completed",)
        )
        assert result == 0
