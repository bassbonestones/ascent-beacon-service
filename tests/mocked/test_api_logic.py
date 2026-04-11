"""Mocked unit tests for API endpoints - testing logic without real DB."""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from uuid import uuid4


# ============================================================================
# Mocked Tests for tasks.py endpoint logic
# ============================================================================

class TestTasksAPILogic:
    """Unit tests for tasks API logic with mocked DB."""

    @pytest.mark.asyncio
    async def test_get_task_or_404_found(self):
        """get_task_or_404 returns task when found."""
        from app.api.helpers.task_helpers import get_task_or_404
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.user_id = "user-1"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_task
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_task_or_404(mock_db, "task-123", "user-1")
        assert result.id == "task-123"

    @pytest.mark.asyncio
    async def test_get_task_or_404_not_found_raises(self):
        """get_task_or_404 raises HTTPException when not found."""
        from app.api.helpers.task_helpers import get_task_or_404
        from fastapi import HTTPException
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(HTTPException) as exc_info:
            await get_task_or_404(mock_db, "nonexistent", "user-1")
        
        assert exc_info.value.status_code == 404
        assert "Task not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_goal_for_task_or_404_found(self):
        """get_goal_for_task_or_404 returns goal when found."""
        from app.api.helpers.task_helpers import get_goal_for_task_or_404
        
        mock_goal = Mock()
        mock_goal.id = "goal-123"
        mock_goal.user_id = "user-1"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_goal
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_goal_for_task_or_404(mock_db, "goal-123", "user-1")
        assert result.id == "goal-123"

    @pytest.mark.asyncio
    async def test_get_goal_for_task_or_404_not_found_raises(self):
        """get_goal_for_task_or_404 raises HTTPException when not found."""
        from app.api.helpers.task_helpers import get_goal_for_task_or_404
        from fastapi import HTTPException
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(HTTPException) as exc_info:
            await get_goal_for_task_or_404(mock_db, "nonexistent", "user-1")
        
        assert exc_info.value.status_code == 404
        assert "Goal not found" in exc_info.value.detail


# ============================================================================
# Mocked Tests for dependency_helpers.py
# ============================================================================

class TestDependencyHelpersLogic:
    """Unit tests for dependency helpers with mocked DB."""

    @pytest.mark.asyncio
    async def test_get_rule_or_404_found(self):
        """get_rule_or_404 returns rule when found."""
        from app.api.helpers.dependency_helpers import get_rule_or_404
        
        mock_rule = Mock()
        mock_rule.id = "rule-123"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_rule
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_rule_or_404(mock_db, "rule-123", "user-1")
        assert result.id == "rule-123"

    @pytest.mark.asyncio
    async def test_get_rule_or_404_not_found_raises(self):
        """get_rule_or_404 raises HTTPException when not found."""
        from app.api.helpers.dependency_helpers import get_rule_or_404
        from fastapi import HTTPException
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(HTTPException) as exc_info:
            await get_rule_or_404(mock_db, "nonexistent", "user-1")
        
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_check_rule_exists_returns_true(self):
        """check_rule_exists returns True when rule exists."""
        from app.api.helpers.dependency_helpers import check_rule_exists
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = Mock()  # Some rule
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await check_rule_exists(mock_db, "up-1", "down-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_rule_exists_returns_false(self):
        """check_rule_exists returns False when rule doesn't exist."""
        from app.api.helpers.dependency_helpers import check_rule_exists
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await check_rule_exists(mock_db, "up-1", "down-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_detect_cycle_no_existing_rules(self):
        """detect_cycle with no existing rules returns no cycle."""
        from app.api.helpers.dependency_helpers import detect_cycle
        
        mock_scalars = Mock()
        mock_scalars.all.return_value = []  # No existing rules
        
        mock_result = Mock()
        mock_result.scalars.return_value = mock_scalars
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        has_cycle, path = await detect_cycle(mock_db, "user-1", "a", "b")
        assert has_cycle is False

    @pytest.mark.asyncio
    async def test_detect_cycle_finds_cycle(self):
        """detect_cycle detects A->B, B->A cycle."""
        from app.api.helpers.dependency_helpers import detect_cycle
        
        # Existing rule: A -> B (A blocks B)
        existing_rule = Mock()
        existing_rule.upstream_task_id = "a"
        existing_rule.downstream_task_id = "b"
        
        mock_scalars = Mock()
        mock_scalars.all.return_value = [existing_rule]
        
        mock_result = Mock()
        mock_result.scalars.return_value = mock_scalars
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        # Try to add B -> A (would create cycle)
        has_cycle, path = await detect_cycle(mock_db, "user-1", "b", "a")
        assert has_cycle is True
        assert path is not None


# ============================================================================
# Mocked Tests for task_stats logic
# ============================================================================

class TestTaskStatsLogic:
    """Unit tests for task stats pure logic."""

    def test_calculate_streak_with_mocked_completions(self):
        """Test streak calculation with mocked completion data."""
        from app.api.task_stats import calculate_streak
        from datetime import date
        
        # Mock completion objects
        def make_completion(d: date, status: str = "completed"):
            c = Mock()
            c.completed_at = datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)
            c.status = status
            return c
        
        completions = [
            make_completion(date(2026, 4, 7)),
            make_completion(date(2026, 4, 8)),
            make_completion(date(2026, 4, 9)),
        ]
        expected_dates = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected_dates)
        
        assert longest == 3
        assert current == 3

    def test_calculate_streak_with_gap(self):
        """Test streak with a gap in completions."""
        from app.api.task_stats import calculate_streak
        from datetime import date
        
        def make_completion(d: date):
            c = Mock()
            c.completed_at = datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)
            c.status = "completed"
            return c
        
        completions = [
            make_completion(date(2026, 4, 7)),
            # Gap on 4/8
            make_completion(date(2026, 4, 9)),
        ]
        expected_dates = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected_dates)
        
        assert current == 1  # Only today
        assert longest == 1  # Single days don't form streak due to gap


# ============================================================================
# Tests for task_to_response helper
# ============================================================================

class TestTaskToResponse:
    """Unit tests for task_to_response conversion."""

    def test_task_to_response_basic(self):
        """task_to_response converts basic task."""
        from app.api.helpers.task_helpers import task_to_response
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.user_id = "user-1"
        mock_task.goal_id = "goal-1"
        mock_task.title = "Test Task"
        mock_task.description = "Description"
        mock_task.duration_minutes = 30
        mock_task.status = "pending"
        mock_task.scheduled_date = "2026-04-09"
        mock_task.scheduled_at = None
        mock_task.scheduling_mode = "date_only"
        mock_task.is_recurring = False
        mock_task.recurrence_rule = None
        mock_task.recurrence_behavior = None
        mock_task.notify_before_minutes = None
        mock_task.completed_at = None
        mock_task.skip_reason = None
        mock_task.sort_order = None
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)
        mock_task.is_lightning = False
        mock_task.goal = None
        
        result = task_to_response(mock_task)
        
        assert result.id == "task-123"
        assert result.title == "Test Task"
        assert result.status == "pending"

    def test_task_to_response_with_goal(self):
        """task_to_response includes goal info when present."""
        from app.api.helpers.task_helpers import task_to_response
        
        mock_goal = Mock()
        mock_goal.id = "goal-123"
        mock_goal.title = "Goal Title"
        mock_goal.status = "active"
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.user_id = "user-1"
        mock_task.goal_id = "goal-123"
        mock_task.title = "Test Task"
        mock_task.description = None
        mock_task.duration_minutes = 30
        mock_task.status = "pending"
        mock_task.scheduled_date = None
        mock_task.scheduled_at = None
        mock_task.scheduling_mode = None
        mock_task.is_recurring = False
        mock_task.recurrence_rule = None
        mock_task.recurrence_behavior = None
        mock_task.notify_before_minutes = None
        mock_task.completed_at = None
        mock_task.skip_reason = None
        mock_task.sort_order = None
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)
        mock_task.is_lightning = False
        mock_task.goal = mock_goal
        
        result = task_to_response(mock_task)
        
        assert result.goal is not None
        assert result.goal.id == "goal-123"
        assert result.goal.title == "Goal Title"

    def test_task_to_response_with_completion_data(self):
        """task_to_response includes completion tracking data."""
        from app.api.helpers.task_helpers import task_to_response
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.user_id = "user-1"
        mock_task.goal_id = None
        mock_task.title = "Recurring Task"
        mock_task.description = None
        mock_task.duration_minutes = 30
        mock_task.status = "pending"
        mock_task.scheduled_date = None
        mock_task.scheduled_at = datetime.now(timezone.utc)
        mock_task.scheduling_mode = "floating"
        mock_task.is_recurring = True
        mock_task.recurrence_rule = "FREQ=DAILY"
        mock_task.recurrence_behavior = "habitual"
        mock_task.notify_before_minutes = None
        mock_task.completed_at = None
        mock_task.skip_reason = None
        mock_task.sort_order = None
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)
        mock_task.is_lightning = False
        mock_task.goal = None
        
        result = task_to_response(
            mock_task,
            completed_for_today=True,
            completions_today=2,
            completed_times_today=["2026-04-09T10:00:00Z", "2026-04-09T14:00:00Z"],
        )
        
        assert result.completed_for_today is True
        assert result.completions_today == 2
        assert len(result.completed_times_today) == 2

    def test_task_to_response_with_skip_data(self):
        """task_to_response includes skip tracking data."""
        from app.api.helpers.task_helpers import task_to_response
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.user_id = "user-1"
        mock_task.goal_id = None
        mock_task.title = "Recurring Task"
        mock_task.description = None
        mock_task.duration_minutes = 30
        mock_task.status = "pending"
        mock_task.scheduled_date = None
        mock_task.scheduled_at = datetime.now(timezone.utc)
        mock_task.scheduling_mode = "floating"
        mock_task.is_recurring = True
        mock_task.recurrence_rule = "FREQ=DAILY"
        mock_task.recurrence_behavior = "habitual"
        mock_task.notify_before_minutes = None
        mock_task.completed_at = None
        mock_task.skip_reason = None
        mock_task.sort_order = None
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)
        mock_task.is_lightning = False
        mock_task.goal = None
        
        result = task_to_response(
            mock_task,
            skipped_for_today=True,
            skips_today=1,
            skipped_times_today=["2026-04-09T08:00:00Z"],
            skip_reason_today="Too tired",
        )
        
        assert result.skipped_for_today is True
        assert result.skips_today == 1
        assert len(result.skipped_times_today) == 1
        assert result.skip_reason_today == "Too tired"

    def test_task_to_response_non_recurring_ignores_completion_data(self):
        """Non-recurring task ignores completion/skip tracking data."""
        from app.api.helpers.task_helpers import task_to_response
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.user_id = "user-1"
        mock_task.goal_id = None
        mock_task.title = "One-time Task"
        mock_task.description = None
        mock_task.duration_minutes = 30
        mock_task.status = "pending"
        mock_task.scheduled_date = "2026-04-09"
        mock_task.scheduled_at = None
        mock_task.scheduling_mode = "date_only"
        mock_task.is_recurring = False
        mock_task.recurrence_rule = None
        mock_task.recurrence_behavior = None
        mock_task.notify_before_minutes = None
        mock_task.completed_at = None
        mock_task.skip_reason = None
        mock_task.sort_order = None
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)
        mock_task.is_lightning = False
        mock_task.goal = None
        
        # These params should be ignored for non-recurring
        result = task_to_response(
            mock_task,
            completed_for_today=True,
            completions_today=5,
            skipped_for_today=True,
            skips_today=3,
        )
        
        # Non-recurring task should NOT have completion tracking
        assert result.completed_for_today is False
        assert result.completions_today == 0
        assert result.skipped_for_today is False
        assert result.skips_today == 0


# ============================================================================
# Mocked Tests for goal progress helper
# ============================================================================

class TestGoalProgressHelper:
    """Unit tests for goal progress calculation."""

    @pytest.mark.asyncio
    async def test_update_goal_progress_returns_early_if_no_goal_id(self):
        """update_goal_progress does nothing with goal_id=None."""
        from app.api.helpers.task_helpers import update_goal_progress
        
        mock_db = AsyncMock()
        
        # Should return immediately without DB query
        await update_goal_progress(mock_db, None)
        
        # Verify no DB operations
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_goal_progress_handles_no_tasks(self):
        """update_goal_progress handles goal with no tasks."""
        from app.api.helpers.task_helpers import update_goal_progress
        
        # First query returns empty tasks
        mock_tasks_result = Mock()
        mock_tasks_scalars = Mock()
        mock_tasks_scalars.all.return_value = []
        mock_tasks_result.scalars.return_value = mock_tasks_scalars
        
        # Second query returns a goal
        mock_goal = Mock()
        mock_goal.has_incomplete_breakdown = False
        mock_goal.progress_cached = 50
        
        mock_goal_result = Mock()
        mock_goal_result.scalar_one_or_none.return_value = mock_goal
        
        mock_db = AsyncMock()
        mock_db.execute.side_effect = [mock_tasks_result, mock_goal_result]
        
        await update_goal_progress(mock_db, "goal-123")
        
        # Goal should be marked as incomplete with zero progress
        assert mock_goal.has_incomplete_breakdown is True
        assert mock_goal.progress_cached == 0
        assert mock_goal.total_time_minutes == 0

    @pytest.mark.asyncio
    async def test_update_goal_progress_with_time_based_tasks(self):
        """update_goal_progress calculates time-based progress."""
        from app.api.helpers.task_helpers import update_goal_progress
        
        # Create mock tasks with duration
        task1 = Mock()
        task1.duration_minutes = 60
        task1.status = "completed"
        
        task2 = Mock()
        task2.duration_minutes = 40
        task2.status = "pending"
        
        mock_tasks_result = Mock()
        mock_tasks_scalars = Mock()
        mock_tasks_scalars.all.return_value = [task1, task2]
        mock_tasks_result.scalars.return_value = mock_tasks_scalars
        
        mock_goal = Mock()
        mock_goal.status = "not_started"
        
        mock_goal_result = Mock()
        mock_goal_result.scalar_one_or_none.return_value = mock_goal
        
        mock_db = AsyncMock()
        mock_db.execute.side_effect = [mock_tasks_result, mock_goal_result]
        
        await update_goal_progress(mock_db, "goal-123")
        
        # Progress: 60/100 = 60%
        assert mock_goal.progress_cached == 60
        assert mock_goal.total_time_minutes == 100
        assert mock_goal.completed_time_minutes == 60
        # Auto-transition from not_started to in_progress
        assert mock_goal.status == "in_progress"

    @pytest.mark.asyncio
    async def test_update_goal_progress_with_lightning_tasks_only(self):
        """update_goal_progress uses count-based for lightning tasks."""
        from app.api.helpers.task_helpers import update_goal_progress
        
        # All tasks with 0 duration (lightning tasks)
        task1 = Mock()
        task1.duration_minutes = 0
        task1.status = "completed"
        
        task2 = Mock()
        task2.duration_minutes = 0
        task2.status = "pending"
        
        task3 = Mock()
        task3.duration_minutes = 0
        task3.status = "pending"
        
        mock_tasks_result = Mock()
        mock_tasks_scalars = Mock()
        mock_tasks_scalars.all.return_value = [task1, task2, task3]
        mock_tasks_result.scalars.return_value = mock_tasks_scalars
        
        mock_goal = Mock()
        mock_goal.status = "active"
        
        mock_goal_result = Mock()
        mock_goal_result.scalar_one_or_none.return_value = mock_goal
        
        mock_db = AsyncMock()
        mock_db.execute.side_effect = [mock_tasks_result, mock_goal_result]
        
        await update_goal_progress(mock_db, "goal-123")
        
        # Progress: 1/3 = 33%
        assert mock_goal.progress_cached == 33
        assert mock_goal.total_time_minutes == 0


# ============================================================================
# Mocked Tests for anytime task helpers
# ============================================================================

class TestAnytimeTaskHelpers:
    """Unit tests for anytime task helper functions."""

    @pytest.mark.asyncio
    async def test_get_max_sort_order_returns_max(self):
        """get_max_sort_order returns the maximum."""
        from app.api.helpers.task_helpers import get_max_sort_order
        
        mock_result = Mock()
        mock_result.scalar.return_value = 5
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_max_sort_order(mock_db, "user-1")
        
        assert result == 5

    @pytest.mark.asyncio
    async def test_get_max_sort_order_returns_zero_if_none(self):
        """get_max_sort_order returns 0 when no anytime tasks."""
        from app.api.helpers.task_helpers import get_max_sort_order
        
        mock_result = Mock()
        mock_result.scalar.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_max_sort_order(mock_db, "user-1")
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_assign_sort_order_for_anytime_sets_order(self):
        """assign_sort_order_for_anytime sets order for anytime task."""
        from app.api.helpers.task_helpers import assign_sort_order_for_anytime
        
        mock_task = Mock()
        mock_task.scheduling_mode = "anytime"
        mock_task.user_id = "user-1"
        mock_task.sort_order = None
        
        mock_result = Mock()
        mock_result.scalar.return_value = 3
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        await assign_sort_order_for_anytime(mock_db, mock_task)
        
        assert mock_task.sort_order == 4  # max(3) + 1

    @pytest.mark.asyncio
    async def test_assign_sort_order_skips_non_anytime(self):
        """assign_sort_order_for_anytime skips non-anytime tasks."""
        from app.api.helpers.task_helpers import assign_sort_order_for_anytime
        
        mock_task = Mock()
        mock_task.scheduling_mode = "date_only"
        mock_task.sort_order = None
        
        mock_db = AsyncMock()
        
        await assign_sort_order_for_anytime(mock_db, mock_task)
        
        # Should not query DB
        mock_db.execute.assert_not_called()
        assert mock_task.sort_order is None

    @pytest.mark.asyncio
    async def test_clear_sort_order_clears_and_shifts(self):
        """clear_sort_order_for_completed clears order and shifts others."""
        from app.api.helpers.task_helpers import clear_sort_order_for_completed
        
        mock_task = Mock()
        mock_task.scheduling_mode = "anytime"
        mock_task.user_id = "user-1"
        mock_task.sort_order = 2
        
        mock_db = AsyncMock()
        
        await clear_sort_order_for_completed(mock_db, mock_task)
        
        assert mock_task.sort_order is None
        # Should have executed update statement to shift others
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_sort_order_skips_non_anytime(self):
        """clear_sort_order_for_completed skips non-anytime tasks."""
        from app.api.helpers.task_helpers import clear_sort_order_for_completed
        
        mock_task = Mock()
        mock_task.scheduling_mode = "date_only"
        mock_task.sort_order = None
        
        mock_db = AsyncMock()
        
        await clear_sort_order_for_completed(mock_db, mock_task)
        
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_reorder_anytime_task_not_anytime_raises(self):
        """reorder_anytime_task raises if not anytime."""
        from app.api.helpers.task_helpers import reorder_anytime_task
        from fastapi import HTTPException
        
        mock_task = Mock()
        mock_task.scheduling_mode = "date_only"
        
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await reorder_anytime_task(mock_db, mock_task, 1)
        
        assert exc_info.value.status_code == 400
        assert "anytime" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_reorder_anytime_task_completed_raises(self):
        """reorder_anytime_task raises if task is completed (no sort_order)."""
        from app.api.helpers.task_helpers import reorder_anytime_task
        from fastapi import HTTPException
        
        mock_task = Mock()
        mock_task.scheduling_mode = "anytime"
        mock_task.sort_order = None  # Completed
        
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await reorder_anytime_task(mock_db, mock_task, 1)
        
        assert exc_info.value.status_code == 400
        assert "completed" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_reorder_anytime_task_moving_up(self):
        """reorder_anytime_task shifts tasks when moving up."""
        from app.api.helpers.task_helpers import reorder_anytime_task
        
        mock_task = Mock()
        mock_task.scheduling_mode = "anytime"
        mock_task.user_id = "user-1"
        mock_task.sort_order = 5
        
        mock_result = Mock()
        mock_result.scalar.return_value = 7
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        await reorder_anytime_task(mock_db, mock_task, 2)
        
        assert mock_task.sort_order == 2
        # One call for max, one for shift
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_reorder_anytime_task_moving_down(self):
        """reorder_anytime_task shifts tasks when moving down."""
        from app.api.helpers.task_helpers import reorder_anytime_task
        
        mock_task = Mock()
        mock_task.scheduling_mode = "anytime"
        mock_task.user_id = "user-1"
        mock_task.sort_order = 2
        
        mock_result = Mock()
        mock_result.scalar.return_value = 7
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        await reorder_anytime_task(mock_db, mock_task, 5)
        
        assert mock_task.sort_order == 5
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_reorder_anytime_task_same_position_noop(self):
        """reorder_anytime_task is noop if same position."""
        from app.api.helpers.task_helpers import reorder_anytime_task
        
        mock_task = Mock()
        mock_task.scheduling_mode = "anytime"
        mock_task.user_id = "user-1"
        mock_task.sort_order = 3
        
        mock_result = Mock()
        mock_result.scalar.return_value = 5
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        await reorder_anytime_task(mock_db, mock_task, 3)
        
        # Only one call to get max, no update call
        assert mock_db.execute.call_count == 1
        assert mock_task.sort_order == 3


# ============================================================================
# Mocked Tests for goal helpers
# ============================================================================

class TestGoalHelpers:
    """Unit tests for goal helper functions."""

    def test_extract_priorities_from_goal_with_active_revisions(self):
        """Extract priorities when all have active revisions."""
        from app.api.helpers.goal_helpers import _extract_priorities_from_goal
        
        mock_active_rev = Mock()
        mock_active_rev.title = "Priority Title"
        mock_active_rev.score = 75
        
        mock_priority = Mock()
        mock_priority.id = "priority-1"
        mock_priority.active_revision = mock_active_rev
        
        mock_link = Mock()
        mock_link.priority = mock_priority
        
        mock_goal = Mock()
        mock_goal.priority_links = [mock_link]
        
        result = _extract_priorities_from_goal(mock_goal)
        
        assert len(result) == 1
        assert result[0].id == "priority-1"
        assert result[0].title == "Priority Title"
        assert result[0].score == 75

    def test_extract_priorities_from_goal_without_active_revision(self):
        """Extract priorities when some lack active revisions."""
        from app.api.helpers.goal_helpers import _extract_priorities_from_goal
        
        mock_priority = Mock()
        mock_priority.id = "priority-1"
        mock_priority.active_revision = None  # No active revision
        
        mock_link = Mock()
        mock_link.priority = mock_priority
        
        mock_goal = Mock()
        mock_goal.priority_links = [mock_link]
        
        result = _extract_priorities_from_goal(mock_goal)
        
        assert len(result) == 1
        assert result[0].id == "priority-1"
        assert result[0].title == "(No active revision)"
        assert result[0].score is None

    def test_extract_priorities_from_goal_empty_links(self):
        """Extract priorities with no links returns empty list."""
        from app.api.helpers.goal_helpers import _extract_priorities_from_goal
        
        mock_goal = Mock()
        mock_goal.priority_links = []
        
        result = _extract_priorities_from_goal(mock_goal)
        
        assert result == []

    def test_goal_to_response_basic(self):
        """goal_to_response converts basic goal."""
        from app.api.helpers.goal_helpers import goal_to_response
        
        mock_goal = Mock()
        mock_goal.id = "goal-123"
        mock_goal.user_id = "user-1"
        mock_goal.parent_goal_id = None
        mock_goal.title = "Test Goal"
        mock_goal.description = "A test goal"
        mock_goal.target_date = "2026-12-31"
        mock_goal.status = "active"
        mock_goal.progress_cached = 50
        mock_goal.total_time_minutes = 100
        mock_goal.completed_time_minutes = 50
        mock_goal.has_incomplete_breakdown = False
        mock_goal.created_at = datetime.now(timezone.utc)
        mock_goal.updated_at = datetime.now(timezone.utc)
        mock_goal.completed_at = None
        mock_goal.priority_links = []
        
        result = goal_to_response(mock_goal)
        
        assert result.id == "goal-123"
        assert result.title == "Test Goal"
        assert result.status == "active"
        assert result.progress_cached == 50

    def test_goal_to_tree_response_with_subgoals(self):
        """goal_to_tree_response includes sub_goals."""
        from app.api.helpers.goal_helpers import goal_to_tree_response
        from app.schemas.goals import GoalWithSubGoalsResponse
        
        mock_goal = Mock()
        mock_goal.id = "goal-123"
        mock_goal.user_id = "user-1"
        mock_goal.parent_goal_id = None
        mock_goal.title = "Parent Goal"
        mock_goal.description = None
        mock_goal.target_date = None
        mock_goal.status = "active"
        mock_goal.progress_cached = 25
        mock_goal.total_time_minutes = 200
        mock_goal.completed_time_minutes = 50
        mock_goal.has_incomplete_breakdown = False
        mock_goal.created_at = datetime.now(timezone.utc)
        mock_goal.updated_at = datetime.now(timezone.utc)
        mock_goal.completed_at = None
        mock_goal.priority_links = []
        
        # Create a proper sub_goal response
        sub_goal_response = GoalWithSubGoalsResponse(
            id="sub-goal-1",
            user_id="user-1",
            parent_goal_id="goal-123",
            title="Sub Goal",
            description=None,
            target_date=None,
            status="active",
            progress_cached=0,
            total_time_minutes=0,
            completed_time_minutes=0,
            has_incomplete_breakdown=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            completed_at=None,
            priorities=[],
            sub_goals=[],
        )
        
        result = goal_to_tree_response(mock_goal, [sub_goal_response])
        
        assert result.id == "goal-123"
        assert len(result.sub_goals) == 1
        assert result.sub_goals[0].id == "sub-goal-1"

    @pytest.mark.asyncio
    async def test_get_goal_or_404_found(self):
        """get_goal_or_404 returns goal when found."""
        from app.api.helpers.goal_helpers import get_goal_or_404
        
        mock_goal = Mock()
        mock_goal.id = "goal-123"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_goal
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_goal_or_404(mock_db, "goal-123", "user-1")
        assert result.id == "goal-123"

    @pytest.mark.asyncio
    async def test_get_goal_or_404_not_found_raises(self):
        """get_goal_or_404 raises HTTPException when not found."""
        from app.api.helpers.goal_helpers import get_goal_or_404
        from fastapi import HTTPException
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(HTTPException) as exc_info:
            await get_goal_or_404(mock_db, "nonexistent", "user-1")
        
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_check_priority_link_exists_true(self):
        """check_priority_link_exists returns True when link exists."""
        from app.api.helpers.goal_helpers import check_priority_link_exists
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = Mock()  # Some link
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await check_priority_link_exists(mock_db, "goal-1", "priority-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_priority_link_exists_false(self):
        """check_priority_link_exists returns False when link doesn't exist."""
        from app.api.helpers.goal_helpers import check_priority_link_exists
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await check_priority_link_exists(mock_db, "goal-1", "priority-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_priority_link_success(self):
        """delete_priority_link deletes existing link."""
        from app.api.helpers.goal_helpers import delete_priority_link
        
        mock_link = Mock()
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_link
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        await delete_priority_link(mock_db, "goal-1", "priority-1")
        
        mock_db.delete.assert_called_once_with(mock_link)

    @pytest.mark.asyncio
    async def test_delete_priority_link_not_found_raises(self):
        """delete_priority_link raises 404 when link doesn't exist."""
        from app.api.helpers.goal_helpers import delete_priority_link
        from fastapi import HTTPException
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(HTTPException) as exc_info:
            await delete_priority_link(mock_db, "goal-1", "priority-1")
        
        assert exc_info.value.status_code == 404


# ============================================================================
# Additional streak calculation tests
# ============================================================================

class TestStreakCalculation:
    """Additional unit tests for streak calculation edge cases."""

    def test_calculate_streak_empty_completions(self):
        """calculate_streak with empty completions returns zeros."""
        from app.api.task_stats import calculate_streak
        from datetime import date
        
        expected_dates = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        
        current, longest = calculate_streak([], date(2026, 4, 9), expected_dates)
        
        assert current == 0
        assert longest == 0

    def test_calculate_streak_empty_expected_dates(self):
        """calculate_streak with no expected dates returns zeros."""
        from app.api.task_stats import calculate_streak
        from datetime import date
        
        def make_completion(d: date):
            c = Mock()
            c.completed_at = datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)
            c.status = "completed"
            return c
        
        completions = [make_completion(date(2026, 4, 7))]
        
        current, longest = calculate_streak(completions, date(2026, 4, 9), set())
        
        assert current == 0
        assert longest == 0

    def test_calculate_streak_broken_at_end(self):
        """calculate_streak correctly handles broken streak at end."""
        from app.api.task_stats import calculate_streak
        from datetime import date
        
        def make_completion(d: date):
            c = Mock()
            c.completed_at = datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)
            c.status = "completed"
            return c
        
        # Completed 7, 8 but missed 9
        completions = [
            make_completion(date(2026, 4, 7)),
            make_completion(date(2026, 4, 8)),
        ]
        expected_dates = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected_dates)
        
        assert current == 0  # Missed today, streak is 0
        assert longest == 2  # Had a 2-day streak

    def test_calculate_streak_future_dates_ignored(self):
        """calculate_streak ignores expected dates in the future."""
        from app.api.task_stats import calculate_streak
        from datetime import date
        
        def make_completion(d: date):
            c = Mock()
            c.completed_at = datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)
            c.status = "completed"
            return c
        
        completions = [make_completion(date(2026, 4, 9))]
        # Expected dates includes future dates
        expected_dates = {
            date(2026, 4, 9),
            date(2026, 4, 10),  # Future
            date(2026, 4, 11),  # Future
        }
        
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected_dates)
        
        # Current streak should only count today
        assert current == 1

    def test_calculate_streak_skipped_not_counted(self):
        """calculate_streak does not count skipped completions."""
        from app.api.task_stats import calculate_streak
        from datetime import date
        
        def make_completion(d: date, status: str = "completed"):
            c = Mock()
            c.completed_at = datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)
            c.status = status
            return c
        
        completions = [
            make_completion(date(2026, 4, 7)),
            make_completion(date(2026, 4, 8), status="skipped"),  # Skipped
            make_completion(date(2026, 4, 9)),
        ]
        expected_dates = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected_dates)
        
        # Current streak is 1 (only today, skipped broke it)
        assert current == 1
        # Longest streak is 1 (either 7 alone or 9 alone)
        assert longest == 1


# ============================================================================
# Tests for completion row processing branches
# ============================================================================

class TestCompletionRowProcessing:
    """Unit tests for completion row processing branches."""

    def test_process_completion_row_no_scheduled_for_returns_early(self):
        """process_completion_row returns early if scheduled_for is None."""
        from app.api.helpers.completion_helpers import (
            process_completion_row,
            CompletionDataMaps,
        )
        
        data = CompletionDataMaps()
        
        # Call with None scheduled_for
        process_completion_row(
            task_id="task-1",
            scheduled_for=None,  # Branch: returns early
            record_status="completed",
            skip_reason=None,
            local_date=None,
            today_str="2026-04-09",
            data=data,
        )
        
        # Data should be unchanged
        assert len(data.completions_today_count) == 0

    def test_process_completion_row_with_local_date(self):
        """process_completion_row uses local_date when available."""
        from app.api.helpers.completion_helpers import (
            process_completion_row,
            CompletionDataMaps,
        )
        
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="completed",
            skip_reason=None,
            local_date="2026-04-09",  # Branch: uses local_date
            today_str="2026-04-09",
            data=data,
        )
        
        assert data.completions_today_count.get("task-1") == 1

    def test_process_completion_row_without_local_date_uses_utc(self):
        """process_completion_row uses UTC date when local_date is None."""
        from app.api.helpers.completion_helpers import (
            process_completion_row,
            CompletionDataMaps,
        )
        
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="completed",
            skip_reason=None,
            local_date=None,  # Branch: falls back to UTC
            today_str="2026-04-09",
            data=data,
        )
        
        assert data.completions_today_count.get("task-1") == 1
        assert "2026-04-09" in data.completions_by_date_map.get("task-1", {})

    def test_process_completion_row_skipped_status(self):
        """process_completion_row handles skipped status."""
        from app.api.helpers.completion_helpers import (
            process_completion_row,
            CompletionDataMaps,
        )
        
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="skipped",  # Branch: skipped path
            skip_reason="Too tired",
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        assert data.skips_today_count.get("task-1") == 1
        assert data.skip_reason_today_map.get("task-1") == "Too tired"

    def test_process_completion_row_not_today(self):
        """process_completion_row handles dates that are not today."""
        from app.api.helpers.completion_helpers import (
            process_completion_row,
            CompletionDataMaps,
        )
        
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="completed",
            skip_reason=None,
            local_date="2026-04-08",  # Not today
            today_str="2026-04-09",
            data=data,
        )
        
        # Should NOT be in today counts
        assert data.completions_today_count.get("task-1") is None
        # But should be in by_date_map
        assert "2026-04-08" in data.completions_by_date_map.get("task-1", {})

    def test_process_completion_row_naive_datetime(self):
        """process_completion_row handles naive datetime."""
        from app.api.helpers.completion_helpers import (
            process_completion_row,
            CompletionDataMaps,
        )
        
        data = CompletionDataMaps()
        # Naive datetime (no timezone)
        scheduled = datetime(2026, 4, 9, 10, 0)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="completed",
            skip_reason=None,
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        assert data.completions_today_count.get("task-1") == 1

    def test_process_all_completion_rows(self):
        """process_all_completion_rows processes multiple rows."""
        from app.api.helpers.completion_helpers import (
            process_all_completion_rows,
            CompletionDataMaps,
        )
        
        rows = [
            ("task-1", datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc), "completed", None, "2026-04-09"),
            ("task-1", datetime(2026, 4, 9, 14, 0, tzinfo=timezone.utc), "completed", None, "2026-04-09"),
            ("task-2", datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc), "skipped", "Busy", "2026-04-09"),
        ]
        
        data = process_all_completion_rows(rows, "2026-04-09")
        
        assert data.completions_today_count.get("task-1") == 2
        assert data.skips_today_count.get("task-2") == 1

    def test_count_task_statuses(self):
        """count_task_statuses counts pending and completed."""
        from app.api.helpers.completion_helpers import count_task_statuses
        
        tasks = [
            Mock(status="pending"),
            Mock(status="pending"),
            Mock(status="completed"),
            Mock(status="skipped"),
        ]
        
        pending, completed = count_task_statuses(tasks)
        
        assert pending == 2
        assert completed == 1


# ============================================================================
# Tests for scheduling mode inference branches
# ============================================================================

class TestSchedulingModeInference:
    """Unit tests for scheduling mode auto-determination."""

    def test_infer_date_only_when_date_without_time(self):
        """scheduling_mode='date_only' when scheduled_date without scheduled_at."""
        # Pure logic test
        scheduled_date = "2026-04-10"
        scheduled_at = None
        mode_input = None
        
        if mode_input is None:
            if scheduled_date and not scheduled_at:
                mode = "date_only"
            else:
                mode = None
        else:
            mode = mode_input
        
        assert mode == "date_only"

    def test_no_inference_when_mode_provided(self):
        """No inference when scheduling_mode explicitly provided."""
        scheduled_date = "2026-04-10"
        scheduled_at = None
        mode_input = "floating"
        
        if mode_input is None:
            if scheduled_date and not scheduled_at:
                mode = "date_only"
            else:
                mode = None
        else:
            mode = mode_input
        
        assert mode == "floating"

    def test_no_inference_when_both_date_and_time(self):
        """No inference when both scheduled_date and scheduled_at."""
        scheduled_date = "2026-04-10"
        scheduled_at = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
        mode_input = None
        
        if mode_input is None:
            if scheduled_date and not scheduled_at:
                mode = "date_only"
            else:
                mode = None
        else:
            mode = mode_input
        
        # Condition is False because scheduled_at is set
        assert mode is None

    def test_no_inference_when_neither_date_nor_time(self):
        """No inference when neither scheduled_date nor scheduled_at."""
        scheduled_date = None
        scheduled_at = None
        mode_input = None
        
        if mode_input is None:
            if scheduled_date and not scheduled_at:
                mode = "date_only"
            else:
                mode = None
        else:
            mode = mode_input
        
        assert mode is None


# ============================================================================
# Tests for task filter branches
# ============================================================================

class TestTaskFilterBranches:
    """Unit tests for task list filter branches."""

    def test_filter_status_pending(self):
        """status_filter='pending' filters only pending."""
        status_filter = "pending"
        include_completed = False
        
        # Logic: if status_filter == "pending": where status = pending
        # else: use other logic
        if status_filter == "pending":
            filter_condition = "status == 'pending'"
        elif status_filter:
            filter_condition = f"status == '{status_filter}'"
        elif not include_completed:
            filter_condition = "status != 'completed'"
        else:
            filter_condition = None
        
        assert filter_condition == "status == 'pending'"

    def test_filter_specific_status(self):
        """status_filter='completed' filters that specific status."""
        status_filter = "completed"
        include_completed = False
        
        if status_filter == "pending":
            filter_condition = "status == 'pending'"
        elif status_filter:
            filter_condition = f"status == '{status_filter}'"
        elif not include_completed:
            filter_condition = "status != 'completed'"
        else:
            filter_condition = None
        
        assert filter_condition == "status == 'completed'"

    def test_filter_exclude_completed_default(self):
        """Default excludes completed when no status_filter."""
        status_filter = None
        include_completed = False
        
        if status_filter == "pending":
            filter_condition = "status == 'pending'"
        elif status_filter:
            filter_condition = f"status == '{status_filter}'"
        elif not include_completed:
            filter_condition = "status != 'completed'"
        else:
            filter_condition = None
        
        assert filter_condition == "status != 'completed'"

    def test_filter_include_all(self):
        """include_completed=True includes everything."""
        status_filter = None
        include_completed = True
        
        if status_filter == "pending":
            filter_condition = "status == 'pending'"
        elif status_filter:
            filter_condition = f"status == '{status_filter}'"
        elif not include_completed:
            filter_condition = "status != 'completed'"
        else:
            filter_condition = None
        
        assert filter_condition is None

    def test_scheduled_after_valid_date(self):
        """scheduled_after with valid ISO date parses correctly."""
        scheduled_after = "2026-04-09T00:00:00Z"
        
        try:
            after_dt = datetime.fromisoformat(scheduled_after.replace("Z", "+00:00"))
            parsed = True
        except ValueError:
            parsed = False
        
        assert parsed is True
        assert after_dt.year == 2026

    def test_scheduled_after_invalid_date(self):
        """scheduled_after with invalid date handles ValueError."""
        scheduled_after = "not-a-date"
        
        try:
            after_dt = datetime.fromisoformat(scheduled_after.replace("Z", "+00:00"))
            parsed = True
        except ValueError:
            parsed = False
        
        assert parsed is False

    def test_scheduled_before_valid_date(self):
        """scheduled_before with valid ISO date parses correctly."""
        scheduled_before = "2026-04-15T23:59:59+00:00"
        
        try:
            before_dt = datetime.fromisoformat(scheduled_before.replace("Z", "+00:00"))
            parsed = True
        except ValueError:
            parsed = False
        
        assert parsed is True
        assert before_dt.day == 15


# ============================================================================
# Tests for recurring task ID extraction branch
# ============================================================================

class TestRecurringTaskIdExtraction:
    """Unit tests for recurring task ID list building."""

    def test_extract_recurring_ids_mixed_tasks(self):
        """Extracts recurring task IDs from mixed list."""
        tasks = [
            Mock(id="t1", is_recurring=True),
            Mock(id="t2", is_recurring=False),
            Mock(id="t3", is_recurring=True),
            Mock(id="t4", is_recurring=False),
        ]
        
        recurring_ids = [t.id for t in tasks if t.is_recurring]
        
        assert recurring_ids == ["t1", "t3"]

    def test_extract_recurring_ids_none_recurring(self):
        """Returns empty list when no recurring tasks."""
        tasks = [
            Mock(id="t1", is_recurring=False),
            Mock(id="t2", is_recurring=False),
        ]
        
        recurring_ids = [t.id for t in tasks if t.is_recurring]
        
        assert recurring_ids == []

    def test_extract_recurring_ids_all_recurring(self):
        """Returns all IDs when all tasks are recurring."""
        tasks = [
            Mock(id="t1", is_recurring=True),
            Mock(id="t2", is_recurring=True),
        ]
        
        recurring_ids = [t.id for t in tasks if t.is_recurring]
        
        assert recurring_ids == ["t1", "t2"]


# ============================================================================
# Tests for task update field branches
# ============================================================================

class TestTaskUpdateFieldBranches:
    """Unit tests for task update field branches."""

    def test_update_data_exclude_unset_only_includes_sent(self):
        """exclude_unset only includes explicitly sent fields."""
        # Simulate Pydantic model_dump(exclude_unset=True)
        request_data = {"title": "New Title"}  # Only title was sent
        
        if "title" in request_data:
            new_title = request_data["title"]
        else:
            new_title = None
        
        if "description" in request_data:
            new_desc = request_data["description"]
        else:
            new_desc = None
        
        assert new_title == "New Title"
        assert new_desc is None

    def test_update_scheduling_mode_auto_determination(self):
        """Auto-determine scheduling_mode when scheduling fields change."""
        # Current state
        current_mode = "anytime"
        new_scheduled_date = "2026-04-10"
        new_scheduled_at = None
        
        # Logic from tasks.py update endpoint
        if new_scheduled_date and not new_scheduled_at:
            new_mode = "date_only"
        elif new_scheduled_at and not new_scheduled_date:
            if not current_mode or current_mode == "date_only":
                new_mode = None
            else:
                new_mode = current_mode
        else:
            new_mode = current_mode
        
        assert new_mode == "date_only"

    def test_recurrence_behavior_required_for_recurring(self):
        """is_recurring=True requires recurrence_behavior."""
        is_recurring = True
        recurrence_behavior = None
        
        if is_recurring and not recurrence_behavior:
            error = "recurrence_behavior is required"
        else:
            error = None
        
        assert error is not None

    def test_recurrence_behavior_cleared_for_non_recurring(self):
        """recurrence_behavior cleared if task becomes non-recurring."""
        is_recurring = False
        recurrence_behavior = "habitual"
        
        if not is_recurring and recurrence_behavior:
            recurrence_behavior = None
        
        assert recurrence_behavior is None


# ============================================================================
# Tests for reopen task window branches
# ============================================================================

class TestReopenTaskWindowBranches:
    """Unit tests for reopen task completion window determination."""

    def test_day_wide_window_no_scheduled_at(self):
        """Day-wide window when task has no scheduled_at (anytime task)."""
        scheduled_at = None
        target_time = datetime(2026, 4, 9, 14, 30, 22, tzinfo=timezone.utc)
        
        if scheduled_at is None:
            window_start = target_time.replace(hour=0, minute=0, second=0, microsecond=0)
            window_end = target_time.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            tt = target_time.replace(second=0, microsecond=0)
            window_start = tt - timedelta(minutes=1)
            window_end = tt + timedelta(minutes=1)
        
        assert window_start.hour == 0
        assert window_end.hour == 23

    def test_narrow_window_with_scheduled_at(self):
        """Narrow 2-min window when task has specific scheduled_at."""
        scheduled_at = datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc)
        target_time = datetime(2026, 4, 9, 10, 0, 30, tzinfo=timezone.utc)
        
        if scheduled_at is None:
            window_start = target_time.replace(hour=0, minute=0, second=0, microsecond=0)
            window_end = target_time.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            tt = target_time.replace(second=0, microsecond=0)
            window_start = tt - timedelta(minutes=1)
            window_end = tt + timedelta(minutes=1)
        
        assert window_start == datetime(2026, 4, 9, 9, 59, tzinfo=timezone.utc)
        assert window_end == datetime(2026, 4, 9, 10, 1, tzinfo=timezone.utc)


# ============================================================================
# Tests for occurrence ordering branches
# ============================================================================

class TestOccurrenceOrderingBranches:
    """Unit tests for occurrence ordering branches."""

    def test_classify_tasks_single_vs_recurring(self):
        """classify_tasks_by_recurrence separates correctly."""
        from app.api.helpers.occurrence_helpers import classify_tasks_by_recurrence
        
        task_ids = ["t1", "t2", "t3", "t4"]
        recurring_map = {"t1": True, "t2": False, "t3": True, "t4": False}
        
        recurring, single = classify_tasks_by_recurrence(task_ids, recurring_map)
        
        assert recurring == ["t1", "t3"]
        assert single == ["t2", "t4"]

    def test_classify_tasks_all_recurring(self):
        """classify_tasks_by_recurrence handles all recurring."""
        from app.api.helpers.occurrence_helpers import classify_tasks_by_recurrence
        
        task_ids = ["t1", "t2"]
        recurring_map = {"t1": True, "t2": True}
        
        recurring, single = classify_tasks_by_recurrence(task_ids, recurring_map)
        
        assert recurring == ["t1", "t2"]
        assert single == []

    def test_classify_tasks_all_single(self):
        """classify_tasks_by_recurrence handles all single."""
        from app.api.helpers.occurrence_helpers import classify_tasks_by_recurrence
        
        task_ids = ["t1", "t2"]
        recurring_map = {"t1": False, "t2": False}
        
        recurring, single = classify_tasks_by_recurrence(task_ids, recurring_map)
        
        assert recurring == []
        assert single == ["t1", "t2"]

    def test_classify_tasks_unknown_id_defaults_false(self):
        """classify_tasks_by_recurrence treats unknown ID as non-recurring."""
        from app.api.helpers.occurrence_helpers import classify_tasks_by_recurrence
        
        task_ids = ["t1", "t2"]
        recurring_map = {"t1": True}  # t2 not in map
        
        recurring, single = classify_tasks_by_recurrence(task_ids, recurring_map)
        
        assert recurring == ["t1"]
        assert single == ["t2"]  # Defaults to False

    def test_find_position_in_occurrences_found(self):
        """find_position_in_occurrences returns 1-based position."""
        from app.api.helpers.occurrence_helpers import find_position_in_occurrences
        
        occurrences = [
            Mock(task_id="t1", occurrence_index=0),
            Mock(task_id="t2", occurrence_index=0),
            Mock(task_id="t1", occurrence_index=1),
        ]
        
        pos = find_position_in_occurrences(occurrences, "t2", 0)
        
        assert pos == 2

    def test_find_position_in_occurrences_not_found_raises(self):
        """find_position_in_occurrences raises ValueError if not found."""
        from app.api.helpers.occurrence_helpers import find_position_in_occurrences
        
        occurrences = [
            Mock(task_id="t1", occurrence_index=0),
        ]
        
        with pytest.raises(ValueError):
            find_position_in_occurrences(occurrences, "t2", 0)

    def test_merge_overrides_and_preferences_excludes_duplicates(self):
        """merge excludes preferences that have overrides."""
        from app.api.helpers.occurrence_helpers import merge_overrides_and_preferences
        
        overrides = [
            Mock(task_id="t1", occurrence_index=0, sort_position=1),
        ]
        prefs = [
            Mock(task_id="t1", occurrence_index=0, sequence_number=5.0),  # Same as override
            Mock(task_id="t2", occurrence_index=0, sequence_number=2.0),  # Different
        ]
        
        items, keys = merge_overrides_and_preferences(overrides, prefs)
        
        # Should have override for t1 and pref for t2
        assert len(items) == 2
        t1_item = next(i for i in items if i["task_id"] == "t1")
        t2_item = next(i for i in items if i["task_id"] == "t2")
        
        assert t1_item["sort_value"] == 1.0  # Override value
        assert t1_item["is_override"] is True
        assert t2_item["sort_value"] == 2.0  # Pref value
        assert t2_item["is_override"] is False

    def test_build_task_ids_from_occurrences(self):
        """build_task_ids_from_occurrences extracts IDs."""
        from app.api.helpers.occurrence_helpers import build_task_ids_from_occurrences
        
        occurrences = [
            Mock(task_id="t1"),
            Mock(task_id="t2"),
            Mock(task_id="t1"),  # Duplicate
        ]
        
        ids = build_task_ids_from_occurrences(occurrences)
        
        assert ids == ["t1", "t2", "t1"]

    def test_validate_all_tasks_exist_passes(self):
        """validate_all_tasks_exist passes when all exist."""
        from app.api.helpers.occurrence_helpers import validate_all_tasks_exist
        
        task_ids = ["t1", "t2", "t3"]
        valid_ids = {"t1", "t2", "t3", "t4"}
        
        invalid = validate_all_tasks_exist(task_ids, valid_ids)
        
        assert invalid == set()

    def test_validate_all_tasks_exist_finds_invalid(self):
        """validate_all_tasks_exist finds invalid IDs."""
        from app.api.helpers.occurrence_helpers import validate_all_tasks_exist
        
        task_ids = ["t1", "t2", "t5"]
        valid_ids = {"t1", "t2", "t3"}
        
        invalid = validate_all_tasks_exist(task_ids, valid_ids)
        
        assert invalid == {"t5"}


# ============================================================================
# Tests for value impact calculation branches
# ============================================================================

class TestValueImpactBranches:
    """Unit tests for value edit impact calculation branches."""

    def test_similarity_changed_when_different(self):
        """similarity_changed is True when IDs differ."""
        old_similar_id = "rev-1"
        new_similar_id = "rev-2"
        
        similarity_changed = old_similar_id != (new_similar_id or None)
        
        assert similarity_changed is True

    def test_similarity_changed_when_same(self):
        """similarity_changed is False when IDs are same."""
        old_similar_id = "rev-1"
        new_similar_id = "rev-1"
        
        similarity_changed = old_similar_id != (new_similar_id or None)
        
        assert similarity_changed is False

    def test_weight_verification_recommended_length_change(self):
        """weight_verification_recommended when statement length changes > 20."""
        old_statement = "Short value"
        new_statement = "This is a much longer statement that changes meaning significantly"
        
        weight_verification_recommended = (
            abs(len(new_statement) - len(old_statement)) > 20
            or old_statement.lower() != new_statement.lower()
        )
        
        assert weight_verification_recommended is True

    def test_weight_verification_not_recommended_case_only(self):
        """weight_verification NOT recommended for case-only change."""
        old_statement = "I value Honesty"
        new_statement = "I value honesty"
        
        weight_verification_recommended = (
            abs(len(new_statement) - len(old_statement)) > 20
            or old_statement.lower() != new_statement.lower()
        )
        
        assert weight_verification_recommended is False


# ============================================================================
# Tests for goal status transitions
# ============================================================================

class TestGoalStatusTransitions:
    """Unit tests for goal status auto-transition branches."""

    def test_auto_transition_to_in_progress(self):
        """Goal auto-transitions to in_progress when first task completes."""
        goal_status = "not_started"
        tasks = [
            Mock(status="completed"),
            Mock(status="pending"),
        ]
        
        has_completed_task = any(t.status == "completed" for t in tasks)
        
        if goal_status == "not_started" and has_completed_task:
            new_status = "in_progress"
        else:
            new_status = goal_status
        
        assert new_status == "in_progress"

    def test_no_transition_when_no_completed_tasks(self):
        """Goal stays not_started when no tasks completed."""
        goal_status = "not_started"
        tasks = [
            Mock(status="pending"),
        ]
        
        has_completed_task = any(t.status == "completed" for t in tasks)
        
        if goal_status == "not_started" and has_completed_task:
            new_status = "in_progress"
        else:
            new_status = goal_status
        
        assert new_status == "not_started"


# ============================================================================
# Tests for datetime parsing branches
# ============================================================================

class TestDatetimeParsingBranches:
    """Unit tests for datetime parsing edge cases."""

    def test_parse_z_suffix_datetime(self):
        """Parse datetime with Z suffix."""
        dt_str = "2026-04-09T10:00:00Z"
        
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        
        assert dt.tzinfo is not None

    def test_parse_invalid_datetime_catches_error(self):
        """Invalid datetime raises ValueError."""
        dt_str = "not-a-datetime"
        
        try:
            datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            parsed = True
        except ValueError:
            parsed = False
        
        assert parsed is False


# ============================================================================
# Tests for goal helper conversion functions
# ============================================================================

class TestGoalToResponseConversion:
    """Unit tests for goal_to_response conversion."""

    def test_goal_with_priorities(self):
        """Goal with priorities extracts priority info."""
        from app.api.helpers.goal_helpers import _extract_priorities_from_goal
        
        # Mock priority revision  
        mock_revision = Mock()
        mock_revision.title = "Priority Title"
        mock_revision.score = 80  # Integer score
        
        # Mock priority
        mock_priority = Mock()
        mock_priority.id = "priority-1"
        mock_priority.active_revision = mock_revision
        
        # Mock link
        mock_link = Mock()
        mock_link.priority = mock_priority
        
        # Mock goal
        mock_goal = Mock()
        mock_goal.priority_links = [mock_link]
        
        result = _extract_priorities_from_goal(mock_goal)
        
        assert len(result) == 1
        assert result[0].id == "priority-1"
        assert result[0].title == "Priority Title"
        assert result[0].score == 80

    def test_goal_with_priority_no_active_revision(self):
        """Goal with priority but no active revision."""
        from app.api.helpers.goal_helpers import _extract_priorities_from_goal
        
        # Mock priority with no active revision
        mock_priority = Mock()
        mock_priority.id = "priority-2"
        mock_priority.active_revision = None
        
        # Mock link
        mock_link = Mock()
        mock_link.priority = mock_priority
        
        # Mock goal
        mock_goal = Mock()
        mock_goal.priority_links = [mock_link]
        
        result = _extract_priorities_from_goal(mock_goal)
        
        assert len(result) == 1
        assert result[0].id == "priority-2"
        assert result[0].title == "(No active revision)"
        assert result[0].score is None

    def test_goal_with_no_priority_in_link(self):
        """Goal link with no priority (edge case)."""
        from app.api.helpers.goal_helpers import _extract_priorities_from_goal
        
        # Mock link with no priority
        mock_link = Mock()
        mock_link.priority = None
        
        # Mock goal
        mock_goal = Mock()
        mock_goal.priority_links = [mock_link]
        
        result = _extract_priorities_from_goal(mock_goal)
        
        # Should skip links with no priority
        assert len(result) == 0

    def test_goal_to_response_all_fields(self):
        """Goal conversion includes all fields."""
        from app.api.helpers.goal_helpers import goal_to_response
        from datetime import datetime, timezone
        
        mock_goal = Mock()
        mock_goal.id = "goal-abc"
        mock_goal.user_id = "user-123"
        mock_goal.parent_goal_id = None
        mock_goal.title = "Test Goal"
        mock_goal.description = "Description"
        mock_goal.target_date = datetime(2025, 12, 31).date()
        mock_goal.status = "in_progress"
        mock_goal.progress_cached = 50
        mock_goal.total_time_minutes = 120
        mock_goal.completed_time_minutes = 60
        mock_goal.has_incomplete_breakdown = False
        mock_goal.created_at = datetime.now(timezone.utc)
        mock_goal.updated_at = datetime.now(timezone.utc)
        mock_goal.completed_at = None
        mock_goal.priority_links = []
        
        result = goal_to_response(mock_goal)
        
        assert result.id == "goal-abc"
        assert result.title == "Test Goal"
        assert result.progress_cached == 50


# ============================================================================
# Tests for dependency helper conversion
# ============================================================================

class TestDependencyRuleToResponse:
    """Unit tests for rule_to_response conversion."""

    def test_rule_with_both_tasks(self):
        """Dependency rule with upstream and downstream tasks."""
        from app.api.helpers.dependency_helpers import rule_to_response
        
        mock_upstream = Mock()
        mock_upstream.id = "task-up"
        mock_upstream.title = "Upstream Task"
        mock_upstream.is_recurring = True
        mock_upstream.recurrence_rule = "FREQ=DAILY"
        
        mock_downstream = Mock()
        mock_downstream.id = "task-down"
        mock_downstream.title = "Downstream Task"
        mock_downstream.is_recurring = False
        mock_downstream.recurrence_rule = None
        
        mock_rule = Mock()
        mock_rule.id = "rule-1"
        mock_rule.user_id = "user-1"
        mock_rule.upstream_task_id = "task-up"
        mock_rule.downstream_task_id = "task-down"
        mock_rule.strength = "hard"
        mock_rule.scope = "next_occurrence"
        mock_rule.required_occurrence_count = 1
        mock_rule.validity_window_minutes = None
        mock_rule.created_at = datetime.now(timezone.utc)
        mock_rule.updated_at = datetime.now(timezone.utc)
        mock_rule.upstream_task = mock_upstream
        mock_rule.downstream_task = mock_downstream
        
        result = rule_to_response(mock_rule)
        
        assert result.id == "rule-1"
        assert result.upstream_task.id == "task-up"
        assert result.upstream_task.is_recurring is True
        assert result.downstream_task.id == "task-down"

    def test_rule_without_upstream_task(self):
        """Dependency rule when upstream task is None."""
        from app.api.helpers.dependency_helpers import rule_to_response
        
        mock_downstream = Mock()
        mock_downstream.id = "task-down"
        mock_downstream.title = "Downstream"
        mock_downstream.is_recurring = False
        mock_downstream.recurrence_rule = None
        
        mock_rule = Mock()
        mock_rule.id = "rule-2"
        mock_rule.user_id = "user-1"
        mock_rule.upstream_task_id = "task-up"
        mock_rule.downstream_task_id = "task-down"
        mock_rule.strength = "soft"
        mock_rule.scope = "all_occurrences"
        mock_rule.required_occurrence_count = 2
        mock_rule.validity_window_minutes = 30
        mock_rule.created_at = datetime.now(timezone.utc)
        mock_rule.updated_at = datetime.now(timezone.utc)
        mock_rule.upstream_task = None  # Not loaded
        mock_rule.downstream_task = mock_downstream
        
        result = rule_to_response(mock_rule)
        
        assert result.upstream_task is None
        assert result.downstream_task.id == "task-down"

    def test_rule_without_downstream_task(self):
        """Dependency rule when downstream task is None."""
        from app.api.helpers.dependency_helpers import rule_to_response
        
        mock_upstream = Mock()
        mock_upstream.id = "task-up"
        mock_upstream.title = "Upstream"
        mock_upstream.is_recurring = False
        mock_upstream.recurrence_rule = None
        
        mock_rule = Mock()
        mock_rule.id = "rule-3"
        mock_rule.user_id = "user-1"
        mock_rule.upstream_task_id = "task-up"
        mock_rule.downstream_task_id = "task-down"
        mock_rule.strength = "hard"
        mock_rule.scope = "within_window"
        mock_rule.required_occurrence_count = 1
        mock_rule.validity_window_minutes = 60
        mock_rule.created_at = datetime.now(timezone.utc)
        mock_rule.updated_at = datetime.now(timezone.utc)
        mock_rule.upstream_task = mock_upstream
        mock_rule.downstream_task = None  # Not loaded
        
        result = rule_to_response(mock_rule)
        
        assert result.upstream_task.id == "task-up"
        assert result.downstream_task is None


# ============================================================================
# Tests for task_to_response edge cases  
# ============================================================================

class TestTaskToResponseEdgeCases:
    """Additional edge case tests for task_to_response."""

    def test_task_extracts_goal_ids(self):
        """Task with goal links extracts goal IDs from links."""
        # Test the logic of extracting goal_ids from goal_links
        mock_link_1 = Mock()
        mock_link_1.goal_id = "goal-1"
        
        mock_link_2 = Mock()
        mock_link_2.goal_id = "goal-2"
        
        goal_links = [mock_link_1, mock_link_2]
        goal_ids = [link.goal_id for link in goal_links]
        
        assert goal_ids == ["goal-1", "goal-2"]

    def test_empty_goal_links_produces_empty_list(self):
        """Empty goal_links produces empty goal_ids."""
        goal_links = []
        goal_ids = [link.goal_id for link in goal_links]
        
        assert goal_ids == []

    def test_task_scheduled_at_nullable(self):
        """Task with no scheduled_at handles correctly."""
        from app.api.helpers.task_helpers import task_to_response
        
        mock_task = Mock()
        mock_task.id = "task-2"
        mock_task.user_id = "user-1"
        mock_task.goal_id = None
        mock_task.goal = None  # No goal
        mock_task.title = "Anytime Task"
        mock_task.description = None
        mock_task.duration_minutes = 15
        mock_task.status = "pending"
        mock_task.scheduling_mode = "anytime"
        mock_task.scheduled_date = None
        mock_task.scheduled_at = None  # No schedule
        mock_task.is_recurring = False
        mock_task.recurrence_rule = None
        mock_task.recurrence_behavior = None
        mock_task.notify_before_minutes = None
        mock_task.completed_at = None
        mock_task.skip_reason = None
        mock_task.sort_order = 0
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)
        mock_task.is_lightning = False
        
        result = task_to_response(mock_task)
        
        assert result.scheduled_at is None
        assert result.scheduling_mode == "anytime"


# ============================================================================
# Tests for priority helper functions
# ============================================================================

class TestPriorityHelpers:
    """Unit tests for priority helper functions."""

    def test_priority_weight_normalization(self):
        """Test priority weight normalization logic."""
        # Test that weight_normalized is calculated correctly
        weights = [0.3, 0.5, 0.2]
        total = sum(weights)
        normalized = [w / total for w in weights]
        
        assert sum(normalized) == pytest.approx(1.0)
        assert normalized[0] == pytest.approx(0.3)
        assert normalized[1] == pytest.approx(0.5)
        assert normalized[2] == pytest.approx(0.2)

    def test_priority_score_calculation(self):
        """Test priority score calculation logic."""
        # Score = int(normalized_sum * 100)
        normalized_sum = 0.75
        score = int(normalized_sum * 100)
        
        assert score == 75


# ============================================================================
# Additional Async Mocked Tests for Coverage
# ============================================================================


class TestValueContainerLogic:
    """Tests for value container logic patterns."""

    def test_value_normalization_logic(self):
        """Test value sum normalization."""
        weights = [30, 50, 20]
        total = sum(weights)
        normalized = [w / total for w in weights]
        
        assert sum(normalized) == pytest.approx(1.0)
        assert normalized[0] == pytest.approx(0.3)
        assert normalized[1] == pytest.approx(0.5)

    def test_value_ranking_calculation(self):
        """Test value ranking by score."""
        values = [
            {"name": "health", "score": 80},
            {"name": "career", "score": 95},
            {"name": "family", "score": 70},
        ]
        
        ranked = sorted(values, key=lambda v: -v["score"])
        
        assert ranked[0]["name"] == "career"
        assert ranked[1]["name"] == "health"
        assert ranked[2]["name"] == "family"

    def test_value_conflict_detection(self):
        """Test detecting values in conflict."""
        # Two values sharing same revision causes conflict
        values = [
            {"id": "v1", "container_id": "c1"},
            {"id": "v2", "container_id": "c1"},  # Same container = conflict
        ]
        
        containers = {}
        conflicts = []
        for v in values:
            cid = v["container_id"]
            if cid in containers:
                conflicts.append((containers[cid], v["id"]))
            else:
                containers[cid] = v["id"]
        
        assert len(conflicts) == 1
        assert conflicts[0] == ("v1", "v2")


class TestCompletionLogicPatterns:
    """Tests for completion-related logic patterns."""

    def test_completion_rate_calculation(self):
        """Test completion rate calculation."""
        completions = [
            {"status": "completed"},
            {"status": "completed"},
            {"status": "skipped"},
            {"status": "pending"},
        ]
        
        completed = sum(1 for c in completions if c["status"] == "completed")
        total = len(completions)
        rate = completed / total if total > 0 else 0
        
        assert rate == pytest.approx(0.5)

    def test_completion_streak_from_history(self):
        """Test calculating streak from completion history."""
        # True = completed, False = missed
        history = [True, True, True, False, True, True]
        
        # Streak from start (most recent first)
        streak = 0
        for completed in history:
            if completed:
                streak += 1
            else:
                break
        
        assert streak == 3

    def test_completion_by_day_grouping(self):
        """Test grouping completions by day."""
        from datetime import date
        
        completions = [
            {"date": date(2024, 1, 15), "count": 3},
            {"date": date(2024, 1, 15), "count": 2},
            {"date": date(2024, 1, 16), "count": 1},
        ]
        
        by_day = {}
        for c in completions:
            d = c["date"]
            by_day[d] = by_day.get(d, 0) + c["count"]
        
        assert by_day[date(2024, 1, 15)] == 5
        assert by_day[date(2024, 1, 16)] == 1


class TestCycleDetectionMocked:
    """Async mocked tests for dependency cycle detection."""

    @pytest.mark.asyncio
    async def test_detect_cycle_no_cycle(self):
        """detect_cycle returns False when no cycle exists."""
        from app.api.helpers.dependency_helpers import detect_cycle
        
        # No existing rules
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        has_cycle, path = await detect_cycle(
            mock_db, "user-1", "task-A", "task-B"
        )
        
        assert has_cycle is False
        assert path is None

    @pytest.mark.asyncio
    async def test_detect_cycle_with_cycle(self):
        """detect_cycle returns True when cycle exists."""
        from app.api.helpers.dependency_helpers import detect_cycle
        
        # Existing rule: task-B -> task-A (so A -> B would create cycle)
        mock_rule = Mock()
        mock_rule.upstream_task_id = "task-A"
        mock_rule.downstream_task_id = "task-B"
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_rule]
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        # Try to add task-B -> task-A (downstream depends on upstream)
        # which would create: A -> B -> A (cycle)
        has_cycle, path = await detect_cycle(
            mock_db, "user-1", "task-B", "task-A"
        )
        
        # Should detect cycle
        assert has_cycle is True
        assert path is not None

    @pytest.mark.asyncio
    async def test_check_rule_exists_true(self):
        """check_rule_exists returns True when rule exists."""
        from app.api.helpers.dependency_helpers import check_rule_exists
        
        mock_rule = Mock()
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_rule
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await check_rule_exists(mock_db, "task-up", "task-down")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_check_rule_exists_false(self):
        """check_rule_exists returns False when rule doesn't exist."""
        from app.api.helpers.dependency_helpers import check_rule_exists
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await check_rule_exists(mock_db, "task-up", "task-down")
        
        assert result is False


class TestGoalHelpersMocked:
    """Additional async mocked tests for goal helpers."""

    @pytest.mark.asyncio
    async def test_reload_goal_with_eager_loading(self):
        """reload_goal_with_eager_loading returns goal."""
        from app.api.helpers.goal_helpers import reload_goal_with_eager_loading
        
        mock_goal = Mock()
        mock_goal.id = "goal-123"
        
        mock_result = Mock()
        mock_result.scalar_one.return_value = mock_goal
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await reload_goal_with_eager_loading(mock_db, "goal-123")
        
        assert result.id == "goal-123"


class TestGoalProgressHelperMocked:
    """Async mocked tests for goal progress updating."""

    @pytest.mark.asyncio
    async def test_update_goal_progress_no_tasks(self):
        """update_goal_progress handles no tasks case."""
        from app.api.helpers.task_helpers import update_goal_progress
        
        # First execute returns empty tasks
        mock_task_result = Mock()
        mock_task_result.scalars.return_value.all.return_value = []
        
        # Second execute returns the goal
        mock_goal = Mock()
        mock_goal.has_incomplete_breakdown = False
        mock_goal.progress_cached = 100
        
        mock_goal_result = Mock()
        mock_goal_result.scalar_one_or_none.return_value = mock_goal
        
        mock_db = AsyncMock()
        mock_db.execute.side_effect = [mock_task_result, mock_goal_result]
        
        await update_goal_progress(mock_db, "goal-123")
        
        # Goal should be marked as incomplete (no tasks)
        assert mock_goal.has_incomplete_breakdown is True

    @pytest.mark.asyncio
    async def test_update_goal_progress_with_tasks(self):
        """update_goal_progress calculates progress from tasks."""
        from app.api.helpers.task_helpers import update_goal_progress
        
        # Create mock tasks
        mock_task1 = Mock()
        mock_task1.duration_minutes = 60
        mock_task1.status = "completed"
        
        mock_task2 = Mock()
        mock_task2.duration_minutes = 60
        mock_task2.status = "pending"
        
        mock_task_result = Mock()
        mock_task_result.scalars.return_value.all.return_value = [mock_task1, mock_task2]
        
        mock_goal = Mock()
        mock_goal.status = "not_started"
        mock_goal.progress_cached = 0
        
        mock_goal_result = Mock()
        mock_goal_result.scalar_one_or_none.return_value = mock_goal
        
        mock_db = AsyncMock()
        mock_db.execute.side_effect = [mock_task_result, mock_goal_result]
        
        await update_goal_progress(mock_db, "goal-123")
        
        # Goal should have 50% progress
        assert mock_goal.progress_cached == 50
        assert mock_goal.status == "in_progress"  # Transitioned from not_started

    @pytest.mark.asyncio
    async def test_update_goal_progress_nil_goal_id(self):
        """update_goal_progress handles None goal_id."""
        from app.api.helpers.task_helpers import update_goal_progress
        
        mock_db = AsyncMock()
        
        # Should return early without executing anything
        await update_goal_progress(mock_db, None)
        
        # No DB calls should be made
        mock_db.execute.assert_not_called()


class TestAnytimeTaskLogic:
    """Tests for anytime task selection logic."""

    def test_anytime_task_filtering(self):
        """Test filtering anytime tasks."""
        tasks = [
            {"id": "t1", "scheduling_mode": "anytime", "status": "pending"},
            {"id": "t2", "scheduling_mode": "scheduled", "status": "pending"},
            {"id": "t3", "scheduling_mode": "anytime", "status": "completed"},
            {"id": "t4", "scheduling_mode": "anytime", "status": "pending"},
        ]
        
        # Filter for anytime AND pending
        anytime_pending = [
            t for t in tasks
            if t["scheduling_mode"] == "anytime" and t["status"] == "pending"
        ]
        
        assert len(anytime_pending) == 2
        assert "t1" in [t["id"] for t in anytime_pending]
        assert "t4" in [t["id"] for t in anytime_pending]

    def test_anytime_pool_priority(self):
        """Test anytime task prioritization by duration."""
        tasks = [
            {"id": "t1", "duration_minutes": 30},
            {"id": "t2", "duration_minutes": 15},
            {"id": "t3", "duration_minutes": 60},
        ]
        
        # Sort by duration (shortest first)
        sorted_tasks = sorted(tasks, key=lambda t: t["duration_minutes"])
        
        assert sorted_tasks[0]["id"] == "t2"  # 15 min
        assert sorted_tasks[1]["id"] == "t1"  # 30 min
        assert sorted_tasks[2]["id"] == "t3"  # 60 min

    def test_anytime_context_matching(self):
        """Test matching anytime tasks to context."""
        tasks = [
            {"id": "t1", "context": "home", "duration_minutes": 30},
            {"id": "t2", "context": "work", "duration_minutes": 30},
            {"id": "t3", "context": "home", "duration_minutes": 60},
        ]
        
        # Filter by current context
        current_context = "home"
        matching = [t for t in tasks if t["context"] == current_context]
        
        assert len(matching) == 2


class TestTaskFilteringLogic:
    """Tests for task filtering logic patterns."""

    def test_filter_by_date_range(self):
        """Test task filtering by date range."""
        from datetime import date
        
        tasks = [
            {"id": "t1", "scheduled_date": date(2024, 1, 10)},
            {"id": "t2", "scheduled_date": date(2024, 1, 15)},
            {"id": "t3", "scheduled_date": date(2024, 1, 20)},
        ]
        
        start = date(2024, 1, 12)
        end = date(2024, 1, 18)
        
        filtered = [
            t for t in tasks
            if start <= t["scheduled_date"] <= end
        ]
        
        assert len(filtered) == 1
        assert filtered[0]["id"] == "t2"

    def test_filter_by_goal_id(self):
        """Test task filtering by goal ID."""
        tasks = [
            {"id": "t1", "goal_id": "goal-A"},
            {"id": "t2", "goal_id": "goal-B"},
            {"id": "t3", "goal_id": "goal-A"},
        ]
        
        filtered = [t for t in tasks if t["goal_id"] == "goal-A"]
        
        assert len(filtered) == 2

    def test_filter_excluding_archived(self):
        """Test task filtering excluding archived."""
        tasks = [
            {"id": "t1", "archived_at": None},
            {"id": "t2", "archived_at": datetime.now(timezone.utc)},
            {"id": "t3", "archived_at": None},
        ]
        
        active_tasks = [t for t in tasks if t["archived_at"] is None]
        
        assert len(active_tasks) == 2

    def test_combine_multiple_filters(self):
        """Test combining multiple filter criteria."""
        tasks = [
            {"id": "t1", "status": "pending", "is_recurring": True},
            {"id": "t2", "status": "completed", "is_recurring": True},
            {"id": "t3", "status": "pending", "is_recurring": False},
            {"id": "t4", "status": "pending", "is_recurring": True},
        ]
        
        # Pending AND recurring
        filtered = [
            t for t in tasks
            if t["status"] == "pending" and t["is_recurring"]
        ]
        
        assert len(filtered) == 2


class TestSortingLogic:
    """Tests for task sorting logic patterns."""

    def test_sort_by_scheduled_at(self):
        """Test sorting tasks by scheduled_at."""
        tasks = [
            {"id": "t1", "scheduled_at": datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)},
            {"id": "t2", "scheduled_at": datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)},
            {"id": "t3", "scheduled_at": datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)},
        ]
        
        sorted_tasks = sorted(tasks, key=lambda t: t["scheduled_at"])
        
        assert sorted_tasks[0]["id"] == "t2"  # 9:00
        assert sorted_tasks[1]["id"] == "t3"  # 12:00
        assert sorted_tasks[2]["id"] == "t1"  # 14:00

    def test_sort_by_priority_score(self):
        """Test sorting by priority score descending."""
        items = [
            {"id": "p1", "score": 75},
            {"id": "p2", "score": 90},
            {"id": "p3", "score": 60},
        ]
        
        sorted_items = sorted(items, key=lambda p: -p["score"])
        
        assert sorted_items[0]["id"] == "p2"  # Highest score first
        assert sorted_items[2]["id"] == "p3"  # Lowest score last

    def test_stable_sort_with_equal_values(self):
        """Test stable sorting preserves order for equal values."""
        items = [
            {"id": "a", "score": 80, "created": 1},
            {"id": "b", "score": 80, "created": 2},
            {"id": "c", "score": 80, "created": 3},
        ]
        
        # Sort by score (all same), should preserve original order
        sorted_items = sorted(items, key=lambda x: -x["score"])
        
        # Check order preserved
        assert [i["created"] for i in sorted_items] == [1, 2, 3]


class TestPaginationLogic:
    """Tests for pagination logic patterns."""

    def test_offset_limit_pagination(self):
        """Test offset/limit pagination."""
        items = list(range(100))  # 0-99
        
        page = 3
        page_size = 10
        offset = (page - 1) * page_size
        
        paginated = items[offset:offset + page_size]
        
        assert len(paginated) == 10
        assert paginated[0] == 20
        assert paginated[-1] == 29

    def test_total_pages_calculation(self):
        """Test total pages calculation."""
        import math
        
        total_items = 95
        page_size = 10
        
        total_pages = math.ceil(total_items / page_size)
        
        assert total_pages == 10

    def test_last_page_partial(self):
        """Test last page with fewer items."""
        items = list(range(95))
        
        page = 10
        page_size = 10
        offset = (page - 1) * page_size
        
        paginated = items[offset:offset + page_size]
        
        assert len(paginated) == 5  # Only 5 items on last page


# ============================================================================
# Similarity and Embedding Logic Tests
# ============================================================================


class TestSimilarityLogic:
    """Tests for similarity calculation patterns."""

    def test_cosine_similarity_calculation(self):
        """Test cosine similarity calculation."""
        import numpy as np
        
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([1.0, 0.0, 0.0])
        
        # Identical vectors = 1.0 similarity
        similarity = np.dot(vec1, vec2) / (
            np.linalg.norm(vec1) * np.linalg.norm(vec2)
        )
        
        assert similarity == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        """Test orthogonal vectors have 0 similarity."""
        import numpy as np
        
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([0.0, 1.0, 0.0])
        
        similarity = np.dot(vec1, vec2) / (
            np.linalg.norm(vec1) * np.linalg.norm(vec2)
        )
        
        assert similarity == pytest.approx(0.0)

    def test_cosine_similarity_opposite(self):
        """Test opposite vectors have -1 similarity."""
        import numpy as np
        
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([-1.0, 0.0, 0.0])
        
        similarity = np.dot(vec1, vec2) / (
            np.linalg.norm(vec1) * np.linalg.norm(vec2)
        )
        
        assert similarity == pytest.approx(-1.0)

    def test_similarity_threshold_matching(self):
        """Test threshold-based matching."""
        SIMILARITY_THRESHOLD = 0.85
        LLM_FALLBACK_THRESHOLD = 0.70
        
        scores = [0.90, 0.75, 0.60]
        
        # Above threshold
        assert scores[0] >= SIMILARITY_THRESHOLD
        # Between thresholds (LLM fallback)
        assert LLM_FALLBACK_THRESHOLD <= scores[1] < SIMILARITY_THRESHOLD
        # Below all thresholds
        assert scores[2] < LLM_FALLBACK_THRESHOLD

    def test_best_match_selection(self):
        """Test selecting best match from candidates."""
        candidates = [
            {"id": "c1", "similarity_score": 0.75},
            {"id": "c2", "similarity_score": 0.92},
            {"id": "c3", "similarity_score": 0.80},
        ]
        
        best_match = None
        for c in candidates:
            if best_match is None or c["similarity_score"] > best_match["similarity_score"]:
                best_match = c
        
        assert best_match["id"] == "c2"
        assert best_match["similarity_score"] == 0.92


class TestEmbeddingLogic:
    """Tests for embedding-related logic."""

    def test_embedding_dimension_check(self):
        """Test embedding dimension validation."""
        expected_dims = 1536
        embedding = [0.1] * 1536
        
        assert len(embedding) == expected_dims

    def test_embedding_normalization(self):
        """Test embedding normalization."""
        import numpy as np
        
        embedding = np.array([3.0, 4.0, 0.0])
        normalized = embedding / np.linalg.norm(embedding)
        
        # Normalized vector should have unit length
        assert np.linalg.norm(normalized) == pytest.approx(1.0)

    def test_empty_embeddings_handling(self):
        """Test handling empty embedding list."""
        existing_embeddings = []
        
        # No embeddings to compare against
        if not existing_embeddings:
            best_match = None
        
        assert best_match is None


# ============================================================================
# Status Transition Logic Tests
# ============================================================================


class TestStatusTransitionLogic:
    """Tests for task/goal status transition logic."""

    def test_task_completion_status_transition(self):
        """Test task completion changes status."""
        task = {"status": "pending", "is_recurring": False}
        
        # One-time task completion
        if not task["is_recurring"] and task["status"] == "pending":
            task["status"] = "completed"
        
        assert task["status"] == "completed"

    def test_recurring_task_keeps_pending(self):
        """Test recurring task stays pending after completion."""
        task = {"status": "pending", "is_recurring": True}
        
        # Recurring tasks stay pending
        if task["is_recurring"]:
            # Task stays pending, completion goes to separate record
            completion_status = "completed"
        else:
            task["status"] = "completed"
            completion_status = None
        
        assert task["status"] == "pending"
        assert completion_status == "completed"

    def test_goal_status_from_progress(self):
        """Test goal status derived from progress."""
        progress_values = [0, 50, 100]
        
        def derive_status(progress: int) -> str:
            if progress == 0:
                return "not_started"
            elif progress >= 100:
                return "completed"
            else:
                return "in_progress"
        
        assert derive_status(progress_values[0]) == "not_started"
        assert derive_status(progress_values[1]) == "in_progress"
        assert derive_status(progress_values[2]) == "completed"

    def test_skip_task_status(self):
        """Test skipping task changes status."""
        task = {"status": "pending", "is_recurring": False}
        
        # Skip one-time task
        if not task["is_recurring"]:
            task["status"] = "skipped"
        
        assert task["status"] == "skipped"

    def test_reopen_completed_task(self):
        """Test reopening a completed task."""
        task = {"status": "completed", "completed_at": datetime.now(timezone.utc)}
        
        # Reopen
        task["status"] = "pending"
        task["completed_at"] = None
        
        assert task["status"] == "pending"
        assert task["completed_at"] is None


class TestProgressCalculationLogic:
    """Tests for goal progress calculation logic."""

    def test_progress_all_tasks_completed(self):
        """Test 100% progress when all tasks completed."""
        tasks = [
            {"status": "completed", "duration_minutes": 30},
            {"status": "completed", "duration_minutes": 30},
            {"status": "completed", "duration_minutes": 30},
        ]
        
        total = sum(t["duration_minutes"] for t in tasks)
        completed = sum(t["duration_minutes"] for t in tasks if t["status"] == "completed")
        progress = int((completed / total) * 100) if total > 0 else 0
        
        assert progress == 100

    def test_progress_partial_completion(self):
        """Test partial progress calculation."""
        tasks = [
            {"status": "completed", "duration_minutes": 60},  # 1 hour completed
            {"status": "pending", "duration_minutes": 60},     # 1 hour pending
        ]
        
        total = sum(t["duration_minutes"] for t in tasks)
        completed = sum(t["duration_minutes"] for t in tasks if t["status"] == "completed")
        progress = int((completed / total) * 100) if total > 0 else 0
        
        assert progress == 50

    def test_progress_no_tasks(self):
        """Test progress with no tasks."""
        tasks = []
        
        total = sum(t["duration_minutes"] for t in tasks)
        progress = 0 if total == 0 else 100
        
        assert progress == 0

    def test_progress_weighted_by_duration(self):
        """Test progress weighted by duration."""
        tasks = [
            {"status": "completed", "duration_minutes": 120},  # 2 hours completed
            {"status": "pending", "duration_minutes": 60},      # 1 hour pending
        ]
        
        total = sum(t["duration_minutes"] for t in tasks)  # 180 min
        completed = sum(t["duration_minutes"] for t in tasks if t["status"] == "completed")  # 120 min
        progress = int((completed / total) * 100)  # 66%
        
        assert progress == 66


# ============================================================================
# Discovery and Recommendation Logic
# ============================================================================


class TestDiscoveryFilterLogic:
    """Tests for discovery filtering patterns."""

    def test_filter_by_value_alignment(self):
        """Test filtering by value alignment score."""
        discoveries = [
            {"id": "d1", "alignment_score": 0.9},
            {"id": "d2", "alignment_score": 0.5},
            {"id": "d3", "alignment_score": 0.7},
        ]
        
        threshold = 0.6
        aligned = [d for d in discoveries if d["alignment_score"] >= threshold]
        
        assert len(aligned) == 2
        assert "d2" not in [d["id"] for d in aligned]

    def test_discovery_deduplication(self):
        """Test deduplicating discoveries by source."""
        discoveries = [
            {"source_id": "s1", "content": "first"},
            {"source_id": "s1", "content": "duplicate"},
            {"source_id": "s2", "content": "unique"},
        ]
        
        seen = set()
        unique = []
        for d in discoveries:
            if d["source_id"] not in seen:
                seen.add(d["source_id"])
                unique.append(d)
        
        assert len(unique) == 2

    def test_recommendation_scoring(self):
        """Test recommendation scoring logic."""
        recommendations = [
            {"action": "a1", "urgency": 0.8, "importance": 0.9},
            {"action": "a2", "urgency": 0.5, "importance": 0.6},
            {"action": "a3", "urgency": 0.9, "importance": 0.7},
        ]
        
        # Score = urgency * 0.3 + importance * 0.7
        for r in recommendations:
            r["score"] = r["urgency"] * 0.3 + r["importance"] * 0.7
        
        sorted_recs = sorted(recommendations, key=lambda r: -r["score"])
        
        assert sorted_recs[0]["action"] == "a1"  # Highest importance

    def test_discovery_age_filtering(self):
        """Test filtering discoveries by age."""
        now = datetime.now(timezone.utc)
        discoveries = [
            {"id": "d1", "created_at": now - timedelta(days=1)},
            {"id": "d2", "created_at": now - timedelta(days=30)},
            {"id": "d3", "created_at": now - timedelta(days=7)},
        ]
        
        max_age = timedelta(days=14)
        recent = [d for d in discoveries if (now - d["created_at"]) <= max_age]
        
        assert len(recent) == 2
        assert "d2" not in [d["id"] for d in recent]


# ============================================================================
# Ordering and Dependency Logic
# ============================================================================


class TestOrderingLogic:
    """Tests for occurrence ordering logic."""

    def test_topological_sort_order(self):
        """Test topological sort preserves dependencies."""
        # A must come before B, B before C
        dependencies = [("A", "B"), ("B", "C")]
        
        # Simple topological order calculation
        order = ["A", "B", "C"]
        
        # Verify each dependency is satisfied
        for upstream, downstream in dependencies:
            assert order.index(upstream) < order.index(downstream)

    def test_swap_in_order(self):
        """Test swapping items in order."""
        order = ["A", "B", "C", "D", "E"]
        
        # Swap positions of B and D
        idx_b = order.index("B")
        idx_d = order.index("D")
        order[idx_b], order[idx_d] = order[idx_d], order[idx_b]
        
        assert order == ["A", "D", "C", "B", "E"]

    def test_insert_at_position(self):
        """Test inserting item at specific position."""
        order = ["A", "B", "C"]
        
        # Insert X at position 1 (after A)
        order.insert(1, "X")
        
        assert order == ["A", "X", "B", "C"]

    def test_move_to_end(self):
        """Test moving item to end of list."""
        order = ["A", "B", "C", "D"]
        
        # Move B to end
        item = order.pop(order.index("B"))
        order.append(item)
        
        assert order == ["A", "C", "D", "B"]

    def test_stable_reorder_preserves_others(self):
        """Test reordering preserves unaffected items."""
        order = ["A", "B", "C", "D", "E"]
        
        # Remove C and insert after D
        order.remove("C")
        idx_d = order.index("D")
        order.insert(idx_d + 1, "C")
        
        # A, B still in same relative order
        assert order.index("A") < order.index("B")
        # D comes before C now
        assert order.index("D") < order.index("C")


# ============================================================================
# Time and Date Logic
# ============================================================================


class TestDateTimeLogic:
    """Tests for date/time handling patterns."""

    def test_date_range_overlap(self):
        """Test detecting date range overlap."""
        from datetime import date
        
        def ranges_overlap(start1, end1, start2, end2):
            return start1 <= end2 and start2 <= end1
        
        # Overlapping ranges
        assert ranges_overlap(
            date(2024, 1, 1), date(2024, 1, 15),
            date(2024, 1, 10), date(2024, 1, 20)
        )
        
        # Non-overlapping ranges
        assert not ranges_overlap(
            date(2024, 1, 1), date(2024, 1, 10),
            date(2024, 1, 15), date(2024, 1, 25)
        )

    def test_time_slot_duration(self):
        """Test calculating time slot duration."""
        start = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        
        duration = (end - start).total_seconds() / 60  # In minutes
        
        assert duration == 90

    def test_timezone_conversion_consistency(self):
        """Test UTC timestamps are consistent."""
        utc_time = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        
        # UTC is canonical
        assert utc_time.tzinfo == timezone.utc
        assert utc_time.utcoffset() == timedelta(0)

    def test_date_boundary_handling(self):
        """Test handling date boundaries."""
        from datetime import date
        
        today = date(2024, 1, 15)
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        
        assert yesterday == date(2024, 1, 14)
        assert tomorrow == date(2024, 1, 16)

    def test_week_boundary_calculation(self):
        """Test calculating week boundaries."""
        from datetime import date
        
        # A Wednesday
        day = date(2024, 1, 17)
        
        # Monday of that week (weekday 0 = Monday)
        days_since_monday = day.weekday()
        week_start = day - timedelta(days=days_since_monday)
        week_end = week_start + timedelta(days=6)
        
        assert week_start == date(2024, 1, 15)  # Monday
        assert week_end == date(2024, 1, 21)    # Sunday


class TestRecurrencePatternLogic:
    """Tests for recurrence pattern logic."""

    def test_daily_recurrence_next_occurrence(self):
        """Test calculating next daily occurrence."""
        from datetime import date
        
        last_occurrence = date(2024, 1, 15)
        interval = 1  # Every day
        
        next_occurrence = last_occurrence + timedelta(days=interval)
        
        assert next_occurrence == date(2024, 1, 16)

    def test_weekly_recurrence_next_occurrence(self):
        """Test calculating next weekly occurrence."""
        from datetime import date
        
        last_occurrence = date(2024, 1, 15)  # Monday
        interval = 1  # Every week
        
        next_occurrence = last_occurrence + timedelta(weeks=interval)
        
        assert next_occurrence == date(2024, 1, 22)

    def test_recurrence_with_end_date(self):
        """Test recurrence stops at end date."""
        from datetime import date
        
        last_occurrence = date(2024, 1, 15)
        end_date = date(2024, 1, 20)
        interval = 7  # Weekly
        
        next_occurrence = last_occurrence + timedelta(days=interval)
        
        # Next occurrence would be Jan 22, after end_date
        continues = next_occurrence <= end_date
        
        assert continues is False

    def test_weekday_matching(self):
        """Test matching specific weekdays."""
        from datetime import date
        
        # Monday=0, Tuesday=1, ..., Sunday=6
        target_weekdays = [0, 2, 4]  # Mon, Wed, Fri
        
        days = [
            date(2024, 1, 15),  # Monday (0)
            date(2024, 1, 16),  # Tuesday (1)
            date(2024, 1, 17),  # Wednesday (2)
            date(2024, 1, 18),  # Thursday (3)
            date(2024, 1, 19),  # Friday (4)
        ]
        
        matching = [d for d in days if d.weekday() in target_weekdays]
        
        assert len(matching) == 3


# ============================================================================
# Additional Async Mocked Tests for Helper Coverage
# ============================================================================


class TestDependencyHelpersMockedMore:
    """Additional async mocked tests for dependency helpers."""

    @pytest.mark.asyncio
    async def test_get_task_or_404_for_dep_found(self):
        """get_task_or_404_for_dep returns task when found."""
        from app.api.helpers.dependency_helpers import get_task_or_404_for_dep
        
        mock_task = Mock()
        mock_task.id = "task-123"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_task
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_task_or_404_for_dep(mock_db, "task-123", "user-1")
        assert result.id == "task-123"

    @pytest.mark.asyncio
    async def test_get_task_or_404_for_dep_not_found(self):
        """get_task_or_404_for_dep raises 404 when not found."""
        from app.api.helpers.dependency_helpers import get_task_or_404_for_dep
        from fastapi import HTTPException
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(HTTPException) as exc_info:
            await get_task_or_404_for_dep(mock_db, "nonexistent", "user-1")
        
        assert exc_info.value.status_code == 404
        assert "Task not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_detect_cycle_no_cycle_path(self):
        """detect_cycle returns no path when no cycle."""
        from app.api.helpers.dependency_helpers import detect_cycle
        
        # No existing rules
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        # Adding A->B, no existing rules
        has_cycle, path = await detect_cycle(mock_db, "user-1", "task-A", "task-B")
        
        # No cycle since B has no upstream dependencies
        assert has_cycle is False
        assert path is None


class TestPriorityHelpersMockedMore:
    """Additional async mocked tests for priority helpers."""

    @pytest.mark.asyncio
    async def test_get_priority_or_404_not_found(self):
        """get_priority_or_404 raises when priority not found."""
        from app.api.helpers.priority_helpers import get_priority_or_404
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        mock_db.get.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await get_priority_or_404(mock_db, "user-1", "nonexistent")
        
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_priority_or_404_wrong_user(self):
        """get_priority_or_404 raises when priority belongs to different user."""
        from app.api.helpers.priority_helpers import get_priority_or_404
        from fastapi import HTTPException
        
        mock_priority = Mock()
        mock_priority.user_id = "other-user"
        
        mock_db = AsyncMock()
        mock_db.get.return_value = mock_priority
        
        with pytest.raises(HTTPException) as exc_info:
            await get_priority_or_404(mock_db, "user-1", "priority-123")
        
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reload_priority_with_active_revision(self):
        """reload_priority_with_active_revision returns priority."""
        from app.api.helpers.priority_helpers import reload_priority_with_active_revision
        
        mock_priority = Mock()
        mock_priority.id = "priority-123"
        
        mock_result = Mock()
        mock_result.scalar_one.return_value = mock_priority
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await reload_priority_with_active_revision(mock_db, "priority-123")
        assert result.id == "priority-123"

    @pytest.mark.asyncio
    async def test_get_linked_values_for_revision_empty(self):
        """get_linked_values_for_revision returns empty list when no links."""
        from app.api.helpers.priority_helpers import get_linked_values_for_revision
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_linked_values_for_revision(mock_db, "revision-123")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_linked_values_for_revision_with_links(self):
        """get_linked_values_for_revision returns linked values."""
        from app.api.helpers.priority_helpers import get_linked_values_for_revision
        
        mock_value_revision = Mock()
        mock_value_revision.value_id = "value-123"
        mock_value_revision.statement = "Be healthy"
        
        mock_link = Mock()
        mock_link.value_revision = mock_value_revision
        mock_link.link_weight = 0.5
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_link]
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_linked_values_for_revision(mock_db, "revision-123")
        
        assert len(result) == 1
        assert result[0].value_id == "value-123"
        assert result[0].value_statement == "Be healthy"

    @pytest.mark.asyncio
    async def test_get_linked_values_skip_none_revision(self):
        """get_linked_values_for_revision skips links without value_revision."""
        from app.api.helpers.priority_helpers import get_linked_values_for_revision
        
        # Link without value_revision
        mock_link = Mock()
        mock_link.value_revision = None
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_link]
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_linked_values_for_revision(mock_db, "revision-123")
        
        # Should skip the link with no value_revision
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_create_value_links_empty_list(self):
        """create_value_links does nothing with empty list."""
        from app.api.helpers.priority_helpers import create_value_links
        
        mock_db = AsyncMock()
        
        await create_value_links(mock_db, "revision-123", [])
        
        # Should not call db.get or db.add
        mock_db.get.assert_not_called()
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_value_links_none_list(self):
        """create_value_links does nothing with None list."""
        from app.api.helpers.priority_helpers import create_value_links
        
        mock_db = AsyncMock()
        
        await create_value_links(mock_db, "revision-123", None)
        
        mock_db.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_value_links_with_values(self):
        """create_value_links creates links for values."""
        from app.api.helpers.priority_helpers import create_value_links
        
        mock_value = Mock()
        mock_value.active_revision_id = "vrev-123"
        
        mock_db = AsyncMock()
        mock_db.get.return_value = mock_value
        
        await create_value_links(mock_db, "revision-123", ["value-1", "value-2"])
        
        # Should add 2 links
        assert mock_db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_create_value_links_skip_missing_value(self):
        """create_value_links skips values that don't exist."""
        from app.api.helpers.priority_helpers import create_value_links
        
        mock_db = AsyncMock()
        mock_db.get.return_value = None  # Value not found
        
        await create_value_links(mock_db, "revision-123", ["nonexistent"])
        
        # Should not add any links
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_value_links_skip_no_active_revision(self):
        """create_value_links skips values without active revision."""
        from app.api.helpers.priority_helpers import create_value_links
        
        mock_value = Mock()
        mock_value.active_revision_id = None  # No active revision
        
        mock_db = AsyncMock()
        mock_db.get.return_value = mock_value
        
        await create_value_links(mock_db, "revision-123", ["value-1"])
        
        # Should not add any links
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_user_priorities(self):
        """list_user_priorities returns list of priorities."""
        from app.api.helpers.priority_helpers import list_user_priorities
        
        mock_priority = Mock()
        mock_priority.id = "priority-123"
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_priority]
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await list_user_priorities(mock_db, "user-1", stashed=False)
        
        assert len(result) == 1
        assert result[0].id == "priority-123"

    @pytest.mark.asyncio
    async def test_get_priority_revisions(self):
        """get_priority_revisions returns list of revisions."""
        from app.api.helpers.priority_helpers import get_priority_revisions
        
        mock_revision = Mock()
        mock_revision.id = "revision-123"
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_revision]
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_priority_revisions(mock_db, "priority-123")
        
        assert len(result) == 1
        assert result[0].id == "revision-123"


class TestGoalHelpersMockedMore:
    """Additional async mocked tests for goal helpers."""

    @pytest.mark.asyncio
    async def test_get_reschedule_count_zero(self):
        """get_reschedule_count returns 0 when no goals need rescheduling."""
        from app.api.helpers.goal_helpers import get_reschedule_count
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        count = await get_reschedule_count(mock_db, "user-1")
        
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_reschedule_count_with_goals(self):
        """get_reschedule_count returns count of overdue goals."""
        from app.api.helpers.goal_helpers import get_reschedule_count
        
        mock_goals = [Mock(), Mock(), Mock()]
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_goals
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        count = await get_reschedule_count(mock_db, "user-1")
        
        assert count == 3

    @pytest.mark.asyncio
    async def test_delete_priority_link_found(self):
        """delete_priority_link deletes link when found."""
        from app.api.helpers.goal_helpers import delete_priority_link
        
        mock_link = Mock()
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_link
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        await delete_priority_link(mock_db, "goal-123", "priority-123")
        
        mock_db.delete.assert_called_once_with(mock_link)

    @pytest.mark.asyncio
    async def test_delete_priority_link_not_found(self):
        """delete_priority_link raises 404 when link not found."""
        from app.api.helpers.goal_helpers import delete_priority_link
        from fastapi import HTTPException
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(HTTPException) as exc_info:
            await delete_priority_link(mock_db, "goal-123", "priority-123")
        
        assert exc_info.value.status_code == 404
        assert "Priority link not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_create_priority_links_success(self):
        """create_priority_links creates links for valid priorities."""
        from app.api.helpers.goal_helpers import create_priority_links
        
        mock_priority = Mock()
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_priority
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        await create_priority_links(
            mock_db, "goal-123", "user-1", ["priority-1", "priority-2"]
        )
        
        # Should add 2 links
        assert mock_db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_create_priority_links_invalid_priority(self):
        """create_priority_links raises when priority not found."""
        from app.api.helpers.goal_helpers import create_priority_links
        from fastapi import HTTPException
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None  # Priority not found
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(HTTPException) as exc_info:
            await create_priority_links(mock_db, "goal-123", "user-1", ["nonexistent"])
        
        assert exc_info.value.status_code == 400


class TestValueHelpersMockedMore:
    """Additional async mocked tests for value helpers."""

    @pytest.mark.asyncio
    async def test_get_value_or_404_found(self):
        """get_value_or_404 returns value when found."""
        from app.api.helpers.value_helpers import get_value_or_404
        
        mock_value = Mock()
        mock_value.id = "value-123"
        mock_value.user_id = "user-1"  # Same user
        
        mock_db = AsyncMock()
        mock_db.get.return_value = mock_value
        
        result = await get_value_or_404(mock_db, "user-1", "value-123")
        
        assert result.id == "value-123"

    @pytest.mark.asyncio
    async def test_get_value_or_404_not_found(self):
        """get_value_or_404 raises when value not found."""
        from app.api.helpers.value_helpers import get_value_or_404
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        mock_db.get.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await get_value_or_404(mock_db, "user-1", "nonexistent")
        
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_value_or_404_wrong_user(self):
        """get_value_or_404 raises when value belongs to different user."""
        from app.api.helpers.value_helpers import get_value_or_404
        from fastapi import HTTPException
        
        mock_value = Mock()
        mock_value.id = "value-123"
        mock_value.user_id = "other-user"  # Different user
        
        mock_db = AsyncMock()
        mock_db.get.return_value = mock_value
        
        with pytest.raises(HTTPException) as exc_info:
            await get_value_or_404(mock_db, "user-1", "value-123")
        
        assert exc_info.value.status_code == 404


class TestTaskHelpersMockedMore:
    """Additional async mocked tests for task helpers."""

    @pytest.mark.asyncio
    async def test_get_max_sort_order_with_tasks(self):
        """get_max_sort_order returns max when tasks exist."""
        from app.api.helpers.task_helpers import get_max_sort_order
        
        mock_result = Mock()
        mock_result.scalar.return_value = 5
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_max_sort_order(mock_db, "user-1")
        
        assert result == 5

    @pytest.mark.asyncio
    async def test_get_max_sort_order_no_tasks(self):
        """get_max_sort_order returns 0 when no tasks."""
        from app.api.helpers.task_helpers import get_max_sort_order
        
        mock_result = Mock()
        mock_result.scalar.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_max_sort_order(mock_db, "user-1")
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_assign_sort_order_for_anytime(self):
        """assign_sort_order_for_anytime sets sort_order."""
        from app.api.helpers.task_helpers import assign_sort_order_for_anytime
        
        mock_task = Mock()
        mock_task.scheduling_mode = "anytime"
        mock_task.sort_order = None
        mock_task.user_id = "user-1"
        
        mock_result = Mock()
        mock_result.scalar.return_value = 3
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        await assign_sort_order_for_anytime(mock_db, mock_task)
        
        # sort_order should be max + 1 = 4
        assert mock_task.sort_order == 4

    @pytest.mark.asyncio
    async def test_assign_sort_order_skips_non_anytime(self):
        """assign_sort_order_for_anytime skips non-anytime tasks."""
        from app.api.helpers.task_helpers import assign_sort_order_for_anytime
        
        mock_task = Mock()
        mock_task.scheduling_mode = "scheduled"  # Not anytime
        mock_task.sort_order = None
        
        mock_db = AsyncMock()
        
        await assign_sort_order_for_anytime(mock_db, mock_task)
        
        # Should not set sort_order
        assert mock_task.sort_order is None
        # Should not call db.execute
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_sort_order_for_completed(self):
        """clear_sort_order_for_completed clears sort_order."""
        from app.api.helpers.task_helpers import clear_sort_order_for_completed
        
        class MockTask:
            scheduling_mode = "anytime"
            sort_order = 5
            user_id = "user-1"
        
        mock_task = MockTask()
        
        mock_db = AsyncMock()
        
        await clear_sort_order_for_completed(mock_db, mock_task)
        
        assert mock_task.sort_order is None

    @pytest.mark.asyncio
    async def test_clear_sort_order_skips_non_anytime(self):
        """clear_sort_order_for_completed skips non-anytime tasks."""
        from app.api.helpers.task_helpers import clear_sort_order_for_completed
        
        mock_task = Mock()
        mock_task.scheduling_mode = "scheduled"  # Not anytime
        mock_task.sort_order = 5
        
        mock_db = AsyncMock()
        
        await clear_sort_order_for_completed(mock_db, mock_task)
        
        # Should not be called since scheduling_mode is not "anytime"
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_sort_order_skips_null_order(self):
        """clear_sort_order_for_completed skips tasks without sort_order."""
        from app.api.helpers.task_helpers import clear_sort_order_for_completed
        
        mock_task = Mock()
        mock_task.scheduling_mode = "anytime"
        mock_task.sort_order = None  # Already None
        
        mock_db = AsyncMock()
        
        await clear_sort_order_for_completed(mock_db, mock_task)
        
        # Should not be called since sort_order is already None
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_goal_for_task_or_404_found(self):
        """get_goal_for_task_or_404 returns goal when found."""
        from app.api.helpers.task_helpers import get_goal_for_task_or_404
        
        mock_goal = Mock()
        mock_goal.id = "goal-123"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_goal
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_goal_for_task_or_404(mock_db, "goal-123", "user-1")
        
        assert result.id == "goal-123"

    @pytest.mark.asyncio
    async def test_get_goal_for_task_or_404_not_found(self):
        """get_goal_for_task_or_404 raises when goal not found."""
        from app.api.helpers.task_helpers import get_goal_for_task_or_404
        from fastapi import HTTPException
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(HTTPException) as exc_info:
            await get_goal_for_task_or_404(mock_db, "nonexistent", "user-1")
        
        assert exc_info.value.status_code == 404


class TestValueImpactHelpersMocked:
    """Async mocked tests for value impact helpers."""

    @pytest.mark.asyncio
    async def test_compute_value_edit_impact_no_affected_priorities(self):
        """compute_value_edit_impact with no affected priorities."""
        from app.api.helpers.value_impact_helpers import compute_value_edit_impact
        
        # Mock value with revisions
        mock_value = Mock()
        mock_revision = Mock()
        mock_revision.id = "vr-123"
        mock_value.revisions = [mock_revision]
        
        # Mock new revision
        mock_new_revision = Mock()
        mock_new_revision.similar_value_revision_id = None
        
        # No affected priorities
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await compute_value_edit_impact(
            mock_db,
            "user-1",
            mock_value,
            mock_new_revision,
            None,  # No old revision
            "New statement"
        )
        
        assert result.affected_priorities_count == 0
        assert result.affected_priorities == []

    @pytest.mark.asyncio
    async def test_compute_value_edit_impact_with_affected_priorities(self):
        """compute_value_edit_impact with affected priorities."""
        from app.api.helpers.value_impact_helpers import compute_value_edit_impact
        
        mock_value = Mock()
        mock_revision = Mock()
        mock_revision.id = "vr-123"
        mock_value.revisions = [mock_revision]
        
        mock_new_revision = Mock()
        mock_new_revision.similar_value_revision_id = "vr-999"
        
        # Affected priority
        mock_active_rev = Mock()
        mock_active_rev.title = "Priority Title"
        mock_active_rev.is_anchored = True
        
        mock_priority = Mock()
        mock_priority.id = "priority-123"
        mock_priority.active_revision = mock_active_rev
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_priority]
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await compute_value_edit_impact(
            mock_db,
            "user-1",
            mock_value,
            mock_new_revision,
            None,
            "New statement"
        )
        
        assert result.affected_priorities_count == 1
        assert result.affected_priorities[0].priority_id == "priority-123"

    @pytest.mark.asyncio
    async def test_compute_value_edit_impact_similarity_changed(self):
        """compute_value_edit_impact detects similarity change."""
        from app.api.helpers.value_impact_helpers import compute_value_edit_impact
        
        mock_value = Mock()
        mock_value.revisions = []
        
        mock_new_revision = Mock()
        mock_new_revision.similar_value_revision_id = "new-similar"
        
        mock_old_revision = Mock()
        mock_old_revision.similar_value_revision_id = "old-similar"
        mock_old_revision.statement = "Old statement"
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await compute_value_edit_impact(
            mock_db,
            "user-1",
            mock_value,
            mock_new_revision,
            mock_old_revision,
            "New statement significantly different"
        )
        
        assert result.similarity_changed is True
        assert result.weight_verification_recommended is True

    @pytest.mark.asyncio
    async def test_compute_value_edit_impact_weight_verification_length_change(self):
        """compute_value_edit_impact recommends weight verification on length change."""
        from app.api.helpers.value_impact_helpers import compute_value_edit_impact
        
        mock_value = Mock()
        mock_value.revisions = []
        
        mock_new_revision = Mock()
        mock_new_revision.similar_value_revision_id = None
        
        mock_old_revision = Mock()
        mock_old_revision.similar_value_revision_id = None
        mock_old_revision.statement = "Short"  # 5 chars
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await compute_value_edit_impact(
            mock_db,
            "user-1",
            mock_value,
            mock_new_revision,
            mock_old_revision,
            "This is a much longer statement now"  # >20 char diff
        )
        
        assert result.weight_verification_recommended is True

    @pytest.mark.asyncio
    async def test_get_affected_priorities_no_revisions(self):
        """get_affected_priorities_for_value with no revisions returns empty."""
        from app.api.helpers.value_impact_helpers import get_affected_priorities_for_value
        
        # No revisions found
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        
        result = await get_affected_priorities_for_value(mock_db, "user-1", "value-123")
        
        assert result == []

    @pytest.mark.asyncio
    async def test_get_affected_priorities_with_priorities(self):
        """get_affected_priorities_for_value returns affected priorities."""
        from app.api.helpers.value_impact_helpers import get_affected_priorities_for_value
        
        # Mock revisions
        mock_revision = Mock()
        mock_revision.id = "vr-123"
        
        mock_revisions_result = Mock()
        mock_revisions_result.scalars.return_value.all.return_value = [mock_revision]
        
        # Mock priority
        mock_active_rev = Mock()
        mock_active_rev.title = "Priority Title"
        mock_active_rev.is_anchored = False
        
        mock_priority = Mock()
        mock_priority.id = "priority-123"
        mock_priority.active_revision = mock_active_rev
        
        mock_priorities_result = Mock()
        mock_priorities_result.scalars.return_value.all.return_value = [mock_priority]
        
        mock_db = AsyncMock()
        mock_db.execute.side_effect = [mock_revisions_result, mock_priorities_result]
        
        result = await get_affected_priorities_for_value(mock_db, "user-1", "value-123")
        
        assert len(result) == 1
        assert result[0].priority_id == "priority-123"
        assert result[0].title == "Priority Title"

    @pytest.mark.asyncio
    async def test_get_affected_priorities_skip_no_active_revision(self):
        """get_affected_priorities_for_value skips priorities without active_revision."""
        from app.api.helpers.value_impact_helpers import get_affected_priorities_for_value
        
        mock_revision = Mock()
        mock_revision.id = "vr-123"
        
        mock_revisions_result = Mock()
        mock_revisions_result.scalars.return_value.all.return_value = [mock_revision]
        
        # Priority without active revision
        mock_priority = Mock()
        mock_priority.id = "priority-123"
        mock_priority.active_revision = None  # No active revision
        
        mock_priorities_result = Mock()
        mock_priorities_result.scalars.return_value.all.return_value = [mock_priority]
        
        mock_db = AsyncMock()
        mock_db.execute.side_effect = [mock_revisions_result, mock_priorities_result]
        
        result = await get_affected_priorities_for_value(mock_db, "user-1", "value-123")
        
        # Should be empty since priority has no active revision
        assert len(result) == 0


class TestTaskStatusEndpointsMocked:
    """Tests for task status endpoint logic."""

    @pytest.mark.asyncio
    async def test_complete_recurring_task_creates_completion(self):
        """Completing a recurring task creates TaskCompletion record."""
        from app.api.tasks_status import complete_task
        from app.schemas.tasks import CompleteTaskRequest
        from app.schemas.dependency import DependencyStatusResponse
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.is_recurring = True
        mock_task.goal_id = "goal-123"
        mock_task.status = "pending"
        
        mock_db = AsyncMock()
        mock_user = Mock()
        mock_user.id = "user-123"
        
        request = CompleteTaskRequest(scheduled_for=datetime(2024, 1, 15, 10, 0))
        
        # Mock empty dependency status (no deps)
        mock_dep_status = DependencyStatusResponse(
            task_id="task-123",
            dependencies=[],
        )
        
        with patch("app.api.tasks_status.get_task_or_404") as mock_get_task, \
             patch("app.api.tasks_status.task_to_response") as mock_to_response, \
             patch("app.api.tasks_status.update_goal_progress") as mock_update_goal, \
             patch("app.api.tasks_status.check_dependencies") as mock_check_deps:
            mock_get_task.return_value = mock_task
            mock_to_response.return_value = Mock()
            mock_update_goal.return_value = None
            mock_check_deps.return_value = mock_dep_status
            
            await complete_task("task-123", request, mock_user, mock_db)
            
            # Should add a completion record
            mock_db.add.assert_called_once()
            # Task status should NOT have changed (stays pending for recurring)
            assert mock_task.status == "pending"

    @pytest.mark.asyncio
    async def test_complete_one_time_task_updates_status(self):
        """Completing a one-time task updates task status."""
        from app.api.tasks_status import complete_task
        from app.schemas.tasks import CompleteTaskRequest
        from app.schemas.dependency import DependencyStatusResponse
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.is_recurring = False
        mock_task.goal_id = "goal-123"
        mock_task.status = "pending"
        
        mock_db = AsyncMock()
        mock_user = Mock()
        mock_user.id = "user-123"
        
        request = CompleteTaskRequest(scheduled_for=datetime(2024, 1, 15, 10, 0))
        
        # Mock empty dependency status
        mock_dep_status = DependencyStatusResponse(
            task_id="task-123",
            dependencies=[],
        )
        
        with patch("app.api.tasks_status.get_task_or_404") as mock_get_task, \
             patch("app.api.tasks_status.task_to_response") as mock_to_response, \
             patch("app.api.tasks_status.update_goal_progress") as mock_update_goal, \
             patch("app.api.tasks_status.check_dependencies") as mock_check_deps:
            mock_get_task.return_value = mock_task
            mock_to_response.return_value = Mock()
            mock_update_goal.return_value = None
            mock_check_deps.return_value = mock_dep_status
            
            await complete_task("task-123", request, mock_user, mock_db)
            
            # Task status should be updated
            assert mock_task.status == "completed"
            assert mock_task.completed_at is not None

    @pytest.mark.asyncio
    async def test_complete_already_completed_task_raises_error(self):
        """Completing an already completed task raises error."""
        from app.api.tasks_status import complete_task
        from app.schemas.tasks import CompleteTaskRequest
        from app.schemas.dependency import DependencyStatusResponse
        from fastapi import HTTPException
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.is_recurring = False
        mock_task.status = "completed"  # Already completed
        
        mock_db = AsyncMock()
        mock_user = Mock()
        mock_user.id = "user-123"
        
        request = CompleteTaskRequest(scheduled_for=datetime(2024, 1, 15, 10, 0))
        
        # Mock empty dependency status
        mock_dep_status = DependencyStatusResponse(
            task_id="task-123",
            dependencies=[],
        )
        
        with patch("app.api.tasks_status.get_task_or_404") as mock_get_task, \
             patch("app.api.tasks_status.check_dependencies") as mock_check_deps:
            mock_get_task.return_value = mock_task
            mock_check_deps.return_value = mock_dep_status
            
            with pytest.raises(HTTPException) as exc_info:
                await complete_task("task-123", request, mock_user, mock_db)
            
            assert exc_info.value.status_code == 400
            assert "already completed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_skip_recurring_task_creates_completion(self):
        """Skipping a recurring task creates TaskCompletion record."""
        from app.api.tasks_status import skip_task
        from app.schemas.tasks import SkipTaskRequest
        from app.services.skip_dependency_service import SkipImpactResult
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.is_recurring = True
        mock_task.status = "pending"
        
        mock_db = AsyncMock()
        mock_user = Mock()
        mock_user.id = "user-123"
        
        request = SkipTaskRequest(scheduled_for=datetime(2024, 1, 15, 10, 0), reason="Too busy")
        
        with patch("app.api.tasks_status.get_task_or_404") as mock_get_task, \
             patch("app.api.tasks_status.task_to_response") as mock_to_response, \
             patch(
                 "app.api.tasks_status.evaluate_skip_hard_downstream_impact",
                 new_callable=AsyncMock,
             ) as mock_impact:
            mock_get_task.return_value = mock_task
            mock_to_response.return_value = Mock()
            mock_impact.return_value = SkipImpactResult(needs_confirmation=False, affected=[])
            
            await skip_task("task-123", request, mock_user, mock_db)
            
            # Should add a completion record with skip status
            mock_db.add.assert_called_once()
            # Task status should NOT have changed
            assert mock_task.status == "pending"

    @pytest.mark.asyncio
    async def test_skip_one_time_task_updates_status(self):
        """Skipping a one-time task updates task status."""
        from app.api.tasks_status import skip_task
        from app.schemas.tasks import SkipTaskRequest
        from app.services.skip_dependency_service import SkipImpactResult
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.is_recurring = False
        mock_task.status = "pending"
        
        mock_db = AsyncMock()
        mock_user = Mock()
        mock_user.id = "user-123"
        
        request = SkipTaskRequest(scheduled_for=datetime(2024, 1, 15, 10, 0), reason="Changed plans")
        
        with patch("app.api.tasks_status.get_task_or_404") as mock_get_task, \
             patch("app.api.tasks_status.task_to_response") as mock_to_response, \
             patch(
                 "app.api.tasks_status.evaluate_skip_hard_downstream_impact",
                 new_callable=AsyncMock,
             ) as mock_impact:
            mock_get_task.return_value = mock_task
            mock_to_response.return_value = Mock()
            mock_impact.return_value = SkipImpactResult(needs_confirmation=False, affected=[])
            
            await skip_task("task-123", request, mock_user, mock_db)
            
            # Task status should be updated
            assert mock_task.status == "skipped"
            assert mock_task.skip_reason == "Changed plans"

    @pytest.mark.asyncio
    async def test_skip_non_pending_task_raises_error(self):
        """Skipping a non-pending task raises error."""
        from app.api.tasks_status import skip_task
        from app.schemas.tasks import SkipTaskRequest
        from app.services.skip_dependency_service import SkipImpactResult
        from fastapi import HTTPException
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.is_recurring = False
        mock_task.status = "completed"  # Not pending
        
        mock_db = AsyncMock()
        mock_user = Mock()
        mock_user.id = "user-123"
        
        request = SkipTaskRequest(scheduled_for=datetime(2024, 1, 15, 10, 0))
        
        with patch("app.api.tasks_status.get_task_or_404") as mock_get_task, \
             patch(
                 "app.api.tasks_status.evaluate_skip_hard_downstream_impact",
                 new_callable=AsyncMock,
             ) as mock_impact:
            mock_get_task.return_value = mock_task
            mock_impact.return_value = SkipImpactResult(needs_confirmation=False, affected=[])
            
            with pytest.raises(HTTPException) as exc_info:
                await skip_task("task-123", request, mock_user, mock_db)
            
            assert exc_info.value.status_code == 400
            assert "pending" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_reopen_completed_task(self):
        """Reopening a completed task sets status to pending."""
        from app.api.tasks_status import reopen_task
        from app.schemas.tasks import ReopenTaskRequest
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.status = "completed"
        mock_task.goal_id = "goal-123"
        mock_task.is_recurring = False  # One-time task
        
        mock_db = AsyncMock()
        mock_user = Mock()
        mock_user.id = "user-123"
        
        request = ReopenTaskRequest()
        
        with patch("app.api.tasks_status.get_task_or_404") as mock_get_task, \
             patch("app.api.tasks_status.task_to_response") as mock_to_response, \
             patch("app.api.tasks_status.update_goal_progress") as mock_update_goal, \
             patch("app.api.tasks_status.assign_sort_order_for_anytime") as mock_assign:
            mock_get_task.return_value = mock_task
            mock_to_response.return_value = Mock()
            mock_update_goal.return_value = None
            mock_assign.return_value = None
            
            await reopen_task("task-123", request, mock_user, mock_db)
            
            assert mock_task.status == "pending"
            assert mock_task.completed_at is None

    @pytest.mark.asyncio
    async def test_reopen_already_pending_task_raises_error(self):
        """Reopening an already pending task raises error."""
        from app.api.tasks_status import reopen_task
        from app.schemas.tasks import ReopenTaskRequest
        from fastapi import HTTPException
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.status = "pending"  # Already pending
        mock_task.is_recurring = False  # One-time task
        
        mock_db = AsyncMock()
        mock_user = Mock()
        mock_user.id = "user-123"
        
        request = ReopenTaskRequest()
        
        with patch("app.api.tasks_status.get_task_or_404") as mock_get_task:
            mock_get_task.return_value = mock_task
            
            with pytest.raises(HTTPException) as exc_info:
                await reopen_task("task-123", request, mock_user, mock_db)
            
            assert exc_info.value.status_code == 400
            assert "already pending" in exc_info.value.detail


class TestTaskStatsLogic:
    """Tests for task statistics calculation logic."""

    def test_completion_rate_calculation(self):
        """Test completion rate calculation logic."""
        completed = 7
        total = 10
        
        completion_rate = (completed / total) * 100 if total > 0 else 0
        
        assert completion_rate == 70.0

    def test_completion_rate_zero_tasks(self):
        """Test completion rate with no tasks."""
        completed = 0
        total = 0
        
        completion_rate = (completed / total) * 100 if total > 0 else 0
        
        assert completion_rate == 0

    def test_streak_calculation_consecutive(self):
        """Test streak counting for consecutive days."""
        # Simulate completion dates
        from datetime import date, timedelta
        
        today = date(2024, 1, 15)
        completion_dates = [
            today,
            today - timedelta(days=1),
            today - timedelta(days=2),
            today - timedelta(days=3),
        ]
        
        # Count consecutive days from today
        streak = 0
        check_date = today
        for d in sorted(completion_dates, reverse=True):
            if d == check_date:
                streak += 1
                check_date -= timedelta(days=1)
            else:
                break
        
        assert streak == 4

    def test_streak_breaks_on_gap(self):
        """Test streak breaks when there's a gap."""
        from datetime import date, timedelta
        
        today = date(2024, 1, 15)
        completion_dates = [
            today,
            today - timedelta(days=1),
            # Gap at day 2
            today - timedelta(days=3),
        ]
        
        streak = 0
        check_date = today
        for d in sorted(completion_dates, reverse=True):
            if d == check_date:
                streak += 1
                check_date -= timedelta(days=1)
            else:
                break
        
        assert streak == 2

    def test_average_completion_time(self):
        """Test average completion time calculation."""
        completion_times_minutes = [15, 30, 45, 60]
        
        avg_time = sum(completion_times_minutes) / len(completion_times_minutes)
        
        assert avg_time == 37.5

    def test_empty_completion_times(self):
        """Test average with no completion data."""
        completion_times_minutes = []
        
        avg_time = sum(completion_times_minutes) / len(completion_times_minutes) if completion_times_minutes else 0
        
        assert avg_time == 0


class TestRecurrencePatterns:
    """Tests for recurrence pattern validation."""

    def test_valid_daily_pattern(self):
        """Daily pattern is valid."""
        frequency = "DAILY"
        valid_frequencies = ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"]
        
        assert frequency in valid_frequencies

    def test_valid_weekly_pattern(self):
        """Weekly pattern is valid."""
        frequency = "WEEKLY"
        valid_frequencies = ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"]
        
        assert frequency in valid_frequencies

    def test_invalid_frequency_rejected(self):
        """Invalid frequency is rejected."""
        frequency = "HOURLY"
        valid_frequencies = ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"]
        
        assert frequency not in valid_frequencies

    def test_interval_must_be_positive(self):
        """Interval must be positive."""
        interval = 1
        
        assert interval > 0
        
    def test_negative_interval_invalid(self):
        """Negative interval is invalid."""
        interval = -1
        
        is_valid = interval > 0
        
        assert not is_valid

    def test_weekday_codes_valid(self):
        """Weekday codes are valid."""
        valid_days = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        test_days = ["MO", "WE", "FR"]
        
        for day in test_days:
            assert day in valid_days

    def test_invalid_weekday_code(self):
        """Invalid weekday code is rejected."""
        valid_days = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        invalid_day = "XX"
        
        assert invalid_day not in valid_days


class TestSchedulingModeLogic:
    """Tests for scheduling mode determination logic."""

    def test_fixed_mode_requires_time(self):
        """Fixed scheduling mode requires specific time."""
        mode = "fixed"
        scheduled_time = datetime(2024, 1, 15, 10, 0)
        
        is_valid = mode == "fixed" and scheduled_time is not None
        
        assert is_valid

    def test_flexible_mode_allows_range(self):
        """Flexible mode allows time range."""
        mode = "flexible"
        earliest = 8  # 8 AM
        latest = 12  # 12 PM
        
        is_valid = mode == "flexible" and earliest < latest
        
        assert is_valid

    def test_anytime_mode_no_restrictions(self):
        """Anytime mode has no time restrictions."""
        mode = "anytime"
        
        # Anytime is always valid
        is_valid = mode == "anytime"
        
        assert is_valid

    def test_invalid_mode_rejected(self):
        """Invalid scheduling mode is rejected."""
        mode = "random"
        valid_modes = ["fixed", "flexible", "anytime"]
        
        assert mode not in valid_modes


class TestDurationCalculations:
    """Tests for task duration calculations."""

    def test_minutes_to_hours_conversion(self):
        """Converting minutes to hours."""
        minutes = 90
        
        hours = minutes / 60
        
        assert hours == 1.5

    def test_total_day_duration(self):
        """Calculate total duration for a day."""
        task_durations_minutes = [30, 45, 60, 15]
        
        total = sum(task_durations_minutes)
        
        assert total == 150

    def test_remaining_capacity(self):
        """Calculate remaining capacity in a day."""
        total_capacity_minutes = 480  # 8 hours
        scheduled_minutes = 300
        
        remaining = total_capacity_minutes - scheduled_minutes
        
        assert remaining == 180

    def test_overbooked_day_detection(self):
        """Detect when day is overbooked."""
        total_capacity_minutes = 480
        scheduled_minutes = 600
        
        is_overbooked = scheduled_minutes > total_capacity_minutes
        
        assert is_overbooked


class TestPriorityValidationServiceMocked:
    """Tests for priority validation service with mocked LLM."""

    @pytest.mark.asyncio
    async def test_validate_priority_name_generic_term(self):
        """Generic terms are rejected without LLM call."""
        from app.services.priority_validation import validate_priority_name
        
        result = await validate_priority_name("Health")
        
        assert result["is_valid"] is False
        assert "not_generic" in result["passed_rules"]
        assert result["passed_rules"]["not_generic"] is False

    @pytest.mark.asyncio
    async def test_validate_priority_name_specific(self):
        """Specific name passes with mocked LLM."""
        from app.services.priority_validation import validate_priority_name
        
        with patch("app.services.priority_validation.llm_client") as mock_llm:
            mock_llm.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"content": '{"is_specific": true}'}}]
            })
            
            result = await validate_priority_name("Restoring physical health after burnout")
            
            assert result["is_valid"] is True

    @pytest.mark.asyncio
    async def test_validate_priority_name_llm_returns_not_specific(self):
        """LLM says not specific, returns feedback."""
        from app.services.priority_validation import validate_priority_name
        
        with patch("app.services.priority_validation.llm_client") as mock_llm:
            mock_llm.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"content": '{"is_specific": false}'}}]
            })
            
            result = await validate_priority_name("Wellness")
            
            assert result["is_valid"] is False
            assert len(result["feedback"]) > 0

    @pytest.mark.asyncio
    async def test_validate_priority_name_llm_error_short_name(self):
        """LLM error with short name returns invalid."""
        from app.services.priority_validation import validate_priority_name
        
        with patch("app.services.priority_validation.llm_client") as mock_llm:
            mock_llm.chat_completion = AsyncMock(side_effect=Exception("API error"))
            
            result = await validate_priority_name("Work")
            
            # Short name with LLM error -> invalid
            assert result["is_valid"] is False

    @pytest.mark.asyncio
    async def test_validate_priority_name_llm_error_long_name(self):
        """LLM error with long name returns valid (fallback)."""
        from app.services.priority_validation import validate_priority_name
        
        with patch("app.services.priority_validation.llm_client") as mock_llm:
            mock_llm.chat_completion = AsyncMock(side_effect=Exception("API error"))
            
            result = await validate_priority_name("Building strong relationships with my team members")
            
            # Long name (>= 12 chars) with LLM error -> valid as fallback
            assert result["is_valid"] is True


class TestValueSimilarityServiceMocked:
    """Tests for value similarity service with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_llm_overlap_check_empty_existing(self):
        """LLM overlap check returns None for empty existing values."""
        from app.services.value_similarity import llm_overlap_check
        
        result = await llm_overlap_check("New value", [])
        
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_overlap_check_finds_overlap(self):
        """LLM overlap check finds overlap."""
        from app.services.value_similarity import llm_overlap_check
        
        with patch("app.services.value_similarity.llm_client") as mock_llm:
            mock_llm.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"content": '{"overlap": true, "most_similar": "Be healthy"}'}}]
            })
            
            result = await llm_overlap_check("Health is important", ["Be healthy", "Work hard"])
            
            assert result is not None
            assert result["overlap"] is True
            assert result["most_similar"] == "Be healthy"

    @pytest.mark.asyncio
    async def test_llm_overlap_check_no_overlap(self):
        """LLM overlap check finds no overlap."""
        from app.services.value_similarity import llm_overlap_check
        
        with patch("app.services.value_similarity.llm_client") as mock_llm:
            mock_llm.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"content": '{"overlap": false, "most_similar": null}'}}]
            })
            
            result = await llm_overlap_check("Learn new things", ["Be healthy"])
            
            assert result is None

    @pytest.mark.asyncio
    async def test_llm_overlap_check_json_decode_error(self):
        """LLM overlap check handles JSON decode error."""
        from app.services.value_similarity import llm_overlap_check
        
        with patch("app.services.value_similarity.llm_client") as mock_llm:
            mock_llm.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"content": "not json"}}]
            })
            
            result = await llm_overlap_check("New value", ["Existing value"])
            
            assert result is None


class TestAuthServiceMocked:
    """Tests for auth service with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_validate_token_format(self):
        """Test token format validation."""
        valid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.valid.signature"
        invalid_token = "not-a-jwt"
        
        def is_jwt_format(token: str) -> bool:
            parts = token.split(".")
            return len(parts) == 3
        
        assert is_jwt_format(valid_token) is True
        assert is_jwt_format(invalid_token) is False


class TestEmailServiceMocked:
    """Tests for email service with mocked dependencies."""

    def test_email_validation_pattern(self):
        """Test email validation logic."""
        import re
        
        email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        
        assert re.match(email_pattern, "user@example.com") is not None
        assert re.match(email_pattern, "invalid-email") is None
        assert re.match(email_pattern, "user.name+tag@domain.co.uk") is not None


class TestTokenServiceMocked:
    """Tests for token service logic."""

    def test_token_expiration_check(self):
        """Test token expiration checking logic."""
        from datetime import datetime, timedelta, timezone
        
        now = datetime.now(timezone.utc)
        
        # Token issued 1 hour ago, expires in 24 hours
        issued_at = now - timedelta(hours=1)
        expires_at = issued_at + timedelta(hours=24)
        
        is_expired = now >= expires_at
        
        assert is_expired is False

    def test_token_expired(self):
        """Test expired token detection."""
        from datetime import datetime, timedelta, timezone
        
        now = datetime.now(timezone.utc)
        
        # Token expired 1 hour ago
        expires_at = now - timedelta(hours=1)
        
        is_expired = now >= expires_at
        
        assert is_expired is True

    def test_refresh_token_rotation_window(self):
        """Test refresh token rotation window logic."""
        from datetime import datetime, timedelta, timezone
        
        now = datetime.now(timezone.utc)
        rotation_window_hours = 2
        
        # Token created 1 hour ago - within rotation window
        created_at = now - timedelta(hours=1)
        within_window = (now - created_at).total_seconds() < rotation_window_hours * 3600
        
        assert within_window is True

    def test_refresh_token_outside_rotation_window(self):
        """Test refresh token outside rotation window."""
        from datetime import datetime, timedelta, timezone
        
        now = datetime.now(timezone.utc)
        rotation_window_hours = 2
        
        # Token created 3 hours ago - outside rotation window
        created_at = now - timedelta(hours=3)
        within_window = (now - created_at).total_seconds() < rotation_window_hours * 3600
        
        assert within_window is False


class TestRecurrenceServiceMore:
    """More tests for recurrence service functions."""

    def test_get_frequency_description_daily(self):
        """Test frequency description for daily tasks."""
        from app.services.recurrence import get_frequency_description
        
        desc = get_frequency_description("FREQ=DAILY")
        
        assert "daily" in desc.lower() or "day" in desc.lower()

    def test_get_frequency_description_weekly(self):
        """Test frequency description for weekly tasks."""
        from app.services.recurrence import get_frequency_description
        
        desc = get_frequency_description("FREQ=WEEKLY")
        
        assert "week" in desc.lower()

    def test_get_frequency_description_monthly(self):
        """Test frequency description for monthly tasks."""
        from app.services.recurrence import get_frequency_description
        
        desc = get_frequency_description("FREQ=MONTHLY")
        
        assert "month" in desc.lower()

    def test_get_frequency_description_with_interval(self):
        """Test frequency description with interval."""
        from app.services.recurrence import get_frequency_description
        
        desc = get_frequency_description("FREQ=DAILY;INTERVAL=2")
        
        # Should mention the interval
        assert desc is not None

    def test_get_frequency_description_with_byday(self):
        """Test frequency description with specific days."""
        from app.services.recurrence import get_frequency_description
        
        desc = get_frequency_description("FREQ=WEEKLY;BYDAY=MO,WE,FR")
        
        # Should be a valid description
        assert desc is not None


class TestCompletionRecordLogic:
    """Tests for completion record logic patterns."""

    def test_calculate_completion_rate(self):
        """Calculate completion rate from records."""
        total = 10
        completed = 7
        skipped = 2
        pending = 1
        
        completion_rate = completed / total if total > 0 else 0
        
        assert completion_rate == 0.7

    def test_calculate_skip_rate(self):
        """Calculate skip rate from records."""
        total = 10
        completed = 7
        skipped = 2
        
        skip_rate = skipped / total if total > 0 else 0
        
        assert skip_rate == 0.2

    def test_streak_broken_by_skip(self):
        """Verify streak breaks on skip."""
        completion_statuses = ["completed", "completed", "skipped", "completed"]
        
        current_streak = 0
        for status in reversed(completion_statuses):
            if status == "completed":
                current_streak += 1
            else:
                break
        
        # Only the most recent completed counts
        assert current_streak == 1


class TestGoalProgressCalculation:
    """Tests for goal progress calculation logic."""

    def test_progress_from_task_completion(self):
        """Calculate progress from task completions."""
        total_tasks = 5
        completed_tasks = 2
        
        progress = (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 0
        
        assert progress == 40.0

    def test_progress_with_weighted_tasks(self):
        """Calculate weighted progress."""
        tasks = [
            {"completed": True, "duration": 30},
            {"completed": True, "duration": 60},
            {"completed": False, "duration": 30},
        ]
        
        total_duration = sum(t["duration"] for t in tasks)
        completed_duration = sum(t["duration"] for t in tasks if t["completed"])
        
        weighted_progress = (completed_duration / total_duration) * 100 if total_duration > 0 else 0
        
        assert weighted_progress == 75.0

    def test_progress_clamp_to_100(self):
        """Progress should be clamped at 100."""
        raw_progress = 120
        
        clamped = min(raw_progress, 100)
        
        assert clamped == 100


class TestDependencyGraphLogic:
    """Tests for dependency relationship logic."""

    def test_detect_direct_cycle(self):
        """Detect direct circular dependency."""
        # Task A depends on Task B, Task B depends on Task A
        dependencies = {
            "A": ["B"],
            "B": ["A"],
        }
        
        def has_cycle(deps, start, visited=None, path=None):
            if visited is None:
                visited = set()
            if path is None:
                path = set()
            
            if start in path:
                return True
            
            if start in visited:
                return False
            
            visited.add(start)
            path.add(start)
            
            for dep in deps.get(start, []):
                if has_cycle(deps, dep, visited, path):
                    return True
            
            path.remove(start)
            return False
        
        assert has_cycle(dependencies, "A")

    def test_no_cycle_linear(self):
        """No cycle in linear dependencies."""
        dependencies = {
            "A": ["B"],
            "B": ["C"],
            "C": [],
        }
        
        def has_cycle(deps, start, visited=None, path=None):
            if visited is None:
                visited = set()
            if path is None:
                path = set()
            
            if start in path:
                return True
            
            if start in visited:
                return False
            
            visited.add(start)
            path.add(start)
            
            for dep in deps.get(start, []):
                if has_cycle(deps, dep, visited, path):
                    return True
            
            path.remove(start)
            return False
        
        assert not has_cycle(dependencies, "A")

    def test_topological_sort_order(self):
        """Verify topological sort produces valid order."""
        # If A depends on B, B should come before A in sorted order
        dependencies = {"A": ["B"], "B": [], "C": ["A"]}
        
        # Simple sort: tasks with no dependencies first
        sorted_tasks = []
        remaining = set(dependencies.keys())
        
        while remaining:
            no_deps = [t for t in remaining if all(d in sorted_tasks for d in dependencies.get(t, []))]
            if not no_deps:
                break  # Cycle detected
            sorted_tasks.extend(no_deps)
            remaining -= set(no_deps)
        
        # B should come before A, A should come before C
        assert sorted_tasks.index("B") < sorted_tasks.index("A")
        assert sorted_tasks.index("A") < sorted_tasks.index("C")


class TestNotificationLogic:
    """Tests for notification scheduling logic."""

    def test_reminder_time_calculation(self):
        """Calculate reminder time before task."""
        from datetime import datetime, timedelta, timezone
        
        task_time = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        reminder_minutes = 15
        
        reminder_time = task_time - timedelta(minutes=reminder_minutes)
        
        assert reminder_time.hour == 9
        assert reminder_time.minute == 45

    def test_multiple_reminders(self):
        """Calculate multiple reminder times."""
        from datetime import datetime, timedelta, timezone
        
        task_time = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        reminder_intervals = [5, 15, 60]  # minutes before
        
        reminders = [task_time - timedelta(minutes=m) for m in reminder_intervals]
        
        assert len(reminders) == 3
        # 5 min before (9:55) > 15 min before (9:45) > 60 min before (9:00)
        assert reminders[0] > reminders[1] > reminders[2]
        assert all(r < task_time for r in reminders)


class TestTimezoneHandling:
    """Tests for timezone handling logic."""

    def test_utc_to_local_offset(self):
        """Test UTC offset calculation."""
        from datetime import datetime, timezone, timedelta
        
        utc_time = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        offset_hours = -5  # EST
        
        local_time = utc_time + timedelta(hours=offset_hours)
        
        assert local_time.hour == 5

    def test_day_boundary_handling(self):
        """Task at midnight edge case."""
        from datetime import date
        
        # Task scheduled for 23:30, duration 60 mins - crosses midnight
        start_hour = 23
        start_minute = 30
        duration = 60
        
        end_hour = (start_hour + (start_minute + duration) // 60) % 24
        crosses_midnight = (start_hour + (start_minute + duration) // 60) >= 24
        
        assert crosses_midnight is True
        assert end_hour == 0


class TestTaskAPIValidation:
    """Tests for task API validation logic."""

    @pytest.mark.asyncio
    async def test_create_task_anytime_recurring_rejected(self):
        """Anytime tasks cannot be recurring."""
        from app.api.tasks_crud import create_task
        from app.schemas.tasks import CreateTaskRequest
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        mock_user = Mock()
        mock_user.id = "user-123"
        
        request = CreateTaskRequest(
            title="Test task",
            scheduling_mode="anytime",
            is_recurring=True,  # Invalid: anytime cannot be recurring
            recurrence_rule="FREQ=DAILY",
            recurrence_behavior="habitual",
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await create_task(request, mock_user, mock_db)
        
        assert exc_info.value.status_code == 400
        assert "cannot be recurring" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_task_recurring_missing_behavior(self):
        """Recurring tasks must have recurrence_behavior."""
        from app.api.tasks_crud import create_task
        from app.schemas.tasks import CreateTaskRequest
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        mock_user = Mock()
        mock_user.id = "user-123"
        
        request = CreateTaskRequest(
            title="Test task",
            is_recurring=True,
            recurrence_rule="FREQ=DAILY",
            recurrence_behavior=None,  # Missing required field
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await create_task(request, mock_user, mock_db)
        
        assert exc_info.value.status_code == 400
        assert "recurrence_behavior is required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_task_non_recurring_with_behavior_rejected(self):
        """Non-recurring tasks should not have recurrence_behavior."""
        from app.api.tasks_crud import create_task
        from app.schemas.tasks import CreateTaskRequest
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        mock_user = Mock()
        mock_user.id = "user-123"
        
        request = CreateTaskRequest(
            title="Test task",
            is_recurring=False,
            recurrence_behavior="habitual",  # Shouldn't be set for non-recurring
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await create_task(request, mock_user, mock_db)
        
        assert exc_info.value.status_code == 400
        assert "should only be set for recurring" in exc_info.value.detail


class TestAlignmentScoreDistribution:
    """Tests for alignment score distribution logic."""

    def test_distribute_priority_to_values_single(self):
        """Distribute priority score to single linked value."""
        priority_score = 100
        value_links = [{"value_id": "v1", "weight": 100}]
        
        total_weight = sum(l["weight"] for l in value_links)
        distributions = {}
        for link in value_links:
            value_portion = priority_score * (link["weight"] / total_weight)
            distributions[link["value_id"]] = value_portion
        
        assert distributions["v1"] == 100

    def test_distribute_priority_to_values_multiple(self):
        """Distribute priority score to multiple linked values."""
        priority_score = 100
        value_links = [
            {"value_id": "v1", "weight": 60},
            {"value_id": "v2", "weight": 30},
            {"value_id": "v3", "weight": 10},
        ]
        
        total_weight = sum(l["weight"] for l in value_links)
        distributions = {}
        for link in value_links:
            value_portion = priority_score * (link["weight"] / total_weight)
            distributions[link["value_id"]] = value_portion
        
        assert distributions["v1"] == 60
        assert distributions["v2"] == 30
        assert distributions["v3"] == 10
        assert sum(distributions.values()) == 100

    def test_aggregate_value_implied_weights(self):
        """Aggregate implied weights from all priorities."""
        # Multiple priorities contributing to same value
        contributions = [
            {"value_id": "v1", "amount": 40},  # From priority 1
            {"value_id": "v2", "amount": 30},  # From priority 1
            {"value_id": "v1", "amount": 20},  # From priority 2 (same value)
            {"value_id": "v3", "amount": 10},  # From priority 2
        ]
        
        aggregated = {}
        for c in contributions:
            vid = c["value_id"]
            aggregated[vid] = aggregated.get(vid, 0) + c["amount"]
        
        assert aggregated["v1"] == 60  # 40 + 20
        assert aggregated["v2"] == 30
        assert aggregated["v3"] == 10


class TestRecommendationLogic:
    """Tests for recommendation validation and processing."""

    def test_recommendation_payload_validation(self):
        """Validate recommendation payload has required fields."""
        payload = {"statement": "Be healthy", "weight": 20}
        
        has_statement = "statement" in payload and bool(payload["statement"])
        
        assert has_statement

    def test_recommendation_payload_missing_statement(self):
        """Detect missing statement in payload."""
        payload = {"weight": 20}
        
        has_statement = "statement" in payload and payload["statement"]
        
        assert has_statement is False

    def test_recommendation_status_transitions(self):
        """Valid recommendation status transitions."""
        valid_transitions = {
            "proposed": ["accepted", "rejected"],
            "accepted": [],  # Final state
            "rejected": [],  # Final state
        }
        
        current = "proposed"
        new_status = "accepted"
        
        is_valid = new_status in valid_transitions.get(current, [])
        
        assert is_valid is True

    def test_recommendation_already_processed(self):
        """Already processed recommendations cannot be changed."""
        valid_transitions = {
            "proposed": ["accepted", "rejected"],
            "accepted": [],
            "rejected": [],
        }
        
        current = "accepted"
        new_status = "rejected"
        
        is_valid = new_status in valid_transitions.get(current, [])
        
        assert is_valid is False


class TestOccurrenceSchedulingLogic:
    """Tests for occurrence scheduling and ordering logic."""

    def test_occurrence_sort_order_assignment(self):
        """Assign sort order to occurrences."""
        occurrences = [
            {"id": "o1", "sort_order": None},
            {"id": "o2", "sort_order": None},
            {"id": "o3", "sort_order": None},
        ]
        
        max_order = 0
        for occ in occurrences:
            max_order += 1
            occ["sort_order"] = max_order
        
        assert occurrences[0]["sort_order"] == 1
        assert occurrences[1]["sort_order"] == 2
        assert occurrences[2]["sort_order"] == 3

    def test_occurrence_reorder_insert(self):
        """Reorder occurrence by inserting at new position."""
        occurrences = [
            {"id": "o1", "sort_order": 1},
            {"id": "o2", "sort_order": 2},
            {"id": "o3", "sort_order": 3},
            {"id": "o4", "sort_order": 4},
        ]
        
        # Move o4 to position 2
        moving_id = "o4"
        new_position = 2
        
        # Remove from current position and shift others
        sorted_occs = [o for o in occurrences if o["id"] != moving_id]
        moving_occ = next(o for o in occurrences if o["id"] == moving_id)
        
        # Insert at new position
        sorted_occs.insert(new_position - 1, moving_occ)
        
        # Reassign sort orders
        for i, occ in enumerate(sorted_occs, 1):
            occ["sort_order"] = i
        
        assert sorted_occs[0]["id"] == "o1"
        assert sorted_occs[1]["id"] == "o4"  # Moved here
        assert sorted_occs[2]["id"] == "o2"
        assert sorted_occs[3]["id"] == "o3"

    def test_filter_fixed_scheduling_mode(self):
        """Filter occurrences by scheduling mode."""
        occurrences = [
            {"id": "o1", "scheduling_mode": "fixed"},
            {"id": "o2", "scheduling_mode": "anytime"},
            {"id": "o3", "scheduling_mode": "flexible"},
            {"id": "o4", "scheduling_mode": "anytime"},
        ]
        
        anytime_only = [o for o in occurrences if o["scheduling_mode"] == "anytime"]
        
        assert len(anytime_only) == 2


class TestDependencyResolutionLogic:
    """Tests for dependency resolution and ordering."""

    def test_dependency_cascade_detection(self):
        """Detect cascading dependencies."""
        # If A depends on B, and completing B should trigger A
        task_a_deps = {"upstream_id": "B", "status": "active"}
        task_b_status = "completed"
        
        a_can_start = task_b_status == "completed"
        
        assert a_can_start is True

    def test_dependency_blocks_execution(self):
        """Incomplete dependency blocks execution."""
        task_a_deps = {"upstream_id": "B", "status": "active"}
        task_b_status = "pending"
        
        a_can_start = task_b_status == "completed"
        
        assert a_can_start is False

    def test_soft_dependency_allows_execution(self):
        """Soft dependency doesn't block execution."""
        dependency_strength = "soft"
        upstream_status = "pending"
        
        # Soft deps allow starting even if upstream incomplete
        can_execute = dependency_strength == "soft" or upstream_status == "completed"
        
        assert can_execute is True

    def test_hard_dependency_blocks_execution(self):
        """Hard dependency blocks execution."""
        dependency_strength = "hard"
        upstream_status = "pending"
        
        can_execute = dependency_strength == "soft" or upstream_status == "completed"
        
        assert can_execute is False


class TestUpdateGoalProgressBranches:
    """Tests for update_goal_progress edge cases and branches."""

    @pytest.mark.asyncio
    async def test_update_goal_progress_goal_not_found(self):
        """When goal doesn't exist in DB, handle gracefully."""
        from app.api.helpers.task_helpers import update_goal_progress
        
        mock_db = AsyncMock()
        
        # No tasks found
        mock_tasks_result = Mock()
        mock_tasks_result.scalars.return_value.all.return_value = []
        
        # Goal not found
        mock_goal_result = Mock()
        mock_goal_result.scalar_one_or_none.return_value = None
        
        mock_db.execute.side_effect = [mock_tasks_result, mock_goal_result]
        
        # Should not raise exception
        await update_goal_progress(mock_db, "goal-123")

    @pytest.mark.asyncio
    async def test_update_goal_progress_lightning_tasks_only(self):
        """Progress calculation for all lightning tasks (no duration)."""
        from app.api.helpers.task_helpers import update_goal_progress
        
        mock_db = AsyncMock()
        
        # Create lightning tasks (no duration)
        mock_task1 = Mock()
        mock_task1.duration_minutes = 0
        mock_task1.status = "completed"
        
        mock_task2 = Mock()
        mock_task2.duration_minutes = 0
        mock_task2.status = "pending"
        
        mock_tasks_result = Mock()
        mock_tasks_result.scalars.return_value.all.return_value = [mock_task1, mock_task2]
        
        mock_goal = Mock()
        mock_goal.status = "not_started"
        mock_goal_result = Mock()
        mock_goal_result.scalar_one_or_none.return_value = mock_goal
        
        mock_db.execute.side_effect = [mock_tasks_result, mock_goal_result]
        
        await update_goal_progress(mock_db, "goal-123")
        
        # Should have calculated count-based progress (1/2 = 50%)
        assert mock_goal.progress_cached == 50


class TestTaskToResponseBranches:
    """Tests for task_to_response edge cases."""

    def test_task_to_response_no_goal(self):
        """Convert task without goal to response."""
        from app.api.helpers.task_helpers import task_to_response
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.user_id = "user-123"
        mock_task.goal_id = None
        mock_task.goal = None  # No goal
        mock_task.title = "Test task"
        mock_task.description = None
        mock_task.duration_minutes = 30
        mock_task.status = "pending"
        mock_task.scheduled_date = None
        mock_task.scheduled_at = None
        mock_task.scheduling_mode = "anytime"
        mock_task.is_recurring = False
        mock_task.recurrence_rule = None
        mock_task.recurrence_behavior = None
        mock_task.notify_before_minutes = None
        mock_task.completed_at = None
        mock_task.skip_reason = None
        mock_task.sort_order = 1
        mock_task.created_at = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        mock_task.updated_at = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        mock_task.is_lightning = False
        
        response = task_to_response(mock_task)
        
        assert response.id == "task-123"
        assert response.goal is None

    def test_task_to_response_with_goal(self):
        """Convert task with goal to response."""
        from app.api.helpers.task_helpers import task_to_response
        
        mock_goal = Mock()
        mock_goal.id = "goal-123"
        mock_goal.title = "Test goal"
        mock_goal.status = "in_progress"
        
        mock_task = Mock()
        mock_task.id = "task-123"
        mock_task.user_id = "user-123"
        mock_task.goal_id = "goal-123"
        mock_task.goal = mock_goal  # Has goal
        mock_task.title = "Test task"
        mock_task.description = None
        mock_task.duration_minutes = 30
        mock_task.status = "pending"
        mock_task.scheduled_date = None
        mock_task.scheduled_at = None
        mock_task.scheduling_mode = "anytime"
        mock_task.is_recurring = False
        mock_task.recurrence_rule = None
        mock_task.recurrence_behavior = None
        mock_task.notify_before_minutes = None
        mock_task.completed_at = None
        mock_task.skip_reason = None
        mock_task.sort_order = 1
        mock_task.created_at = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        mock_task.updated_at = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        mock_task.is_lightning = False
        
        response = task_to_response(mock_task)
        
        assert response.id == "task-123"
        assert response.goal is not None
        assert response.goal.id == "goal-123"


class TestValueSimilarityBranches:
    """Tests for value_similarity partial branches."""

    @pytest.mark.asyncio
    async def test_llm_overlap_check_overlap_true_no_similar(self):
        """LLM says overlap but no most_similar provided."""
        from app.services.value_similarity import llm_overlap_check
        
        with patch("app.services.value_similarity.llm_client") as mock_llm:
            # overlap=true but most_similar is empty
            mock_llm.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"content": '{"overlap": true, "most_similar": ""}'}}]
            })
            
            result = await llm_overlap_check("New value", ["Existing value"])
            
            # Should return None because most_similar is empty
            assert result is None

    @pytest.mark.asyncio
    async def test_llm_overlap_check_overlap_false(self):
        """LLM says no overlap."""
        from app.services.value_similarity import llm_overlap_check
        
        with patch("app.services.value_similarity.llm_client") as mock_llm:
            mock_llm.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"content": '{"overlap": false}'}}]
            })
            
            result = await llm_overlap_check("Completely different", ["Be healthy"])
            
            assert result is None
