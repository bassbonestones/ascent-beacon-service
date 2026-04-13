"""Tests for user model and database fixtures."""

import pytest
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.mark.asyncio
async def test_create_user(db_session: AsyncSession):
    """Test creating a user in the database."""
    user = User(
        id=str(uuid4()),
        display_name="Test User",
        primary_email="testuser@example.com",
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    
    # Query back
    result = await db_session.execute(
        select(User).where(User.id == user.id)
    )
    found = result.scalar_one()
    
    assert found.display_name == "Test User"
    assert found.primary_email == "testuser@example.com"


@pytest.mark.asyncio
async def test_user_fixture(test_user: User):
    """Test that the test_user fixture works."""
    assert test_user.id is not None
    assert test_user.display_name == "Test User"
    assert test_user.is_email_verified is True


# ---- migrated from tests/mocked/test_pure_functions_models.py ----

"""Model property and repr behavior tests."""

from datetime import date


class TestTaskModelProperties:
    def test_is_lightning_property(self):
        from app.models.task import Task

        task = Task()
        task.duration_minutes = 0
        assert task.is_lightning is True
        task.duration_minutes = 5
        assert task.is_lightning is False

    def test_status_properties(self):
        from app.models.task import Task

        task = Task()
        task.status = "completed"
        assert task.is_completed is True
        assert task.is_pending is False
        task.status = "pending"
        assert task.is_completed is False
        assert task.is_pending is True

    def test_scheduling_mode_properties(self):
        from app.models.task import Task

        task = Task()
        task.scheduling_mode = "floating"
        assert task.is_floating is True
        assert task.is_fixed_time is False
        assert task.is_anytime is False

        task.scheduling_mode = "fixed"
        assert task.is_fixed_time is True

        task.scheduling_mode = "anytime"
        assert task.is_anytime is True

    def test_recurrence_behavior_properties(self):
        from app.models.task import Task

        task = Task()
        task.recurrence_behavior = "habitual"
        assert task.is_habitual is True
        assert task.is_essential is False
        task.recurrence_behavior = "essential"
        assert task.is_habitual is False
        assert task.is_essential is True

    def test_task_repr_contains_status_markers(self):
        from app.models.task import Task

        task = Task()
        task.title = "Test Task With a Long Title"
        task.status = "completed"
        task.duration_minutes = 0
        result = repr(task)
        assert "Task" in result
        assert "✓" in result
        assert "⚡" in result


class TestModelReprs:
    def test_goal_repr(self):
        from app.models.goal import Goal

        goal = Goal()
        goal.id = "test-id"
        goal.title = "Test Goal Title That Is Very Long"
        assert "Goal" in repr(goal)

    def test_daily_sort_override_repr(self):
        from app.models.daily_sort_override import DailySortOverride

        override = DailySortOverride()
        override.task_id = "task-123"
        override.override_date = date(2024, 1, 15)
        override.sort_position = 5
        assert "DailySortOverride" in repr(override)

    def test_link_and_preference_repr(self):
        from app.models.goal_priority_link import GoalPriorityLink
        from app.models.occurrence_preference import OccurrencePreference

        link = GoalPriorityLink()
        link.goal_id = "goal-1"
        link.priority_id = "priority-1"
        assert isinstance(repr(link), str)

        pref = OccurrencePreference()
        pref.task_id = "task-1"
        pref.preference_type = "sticky_time"
        assert isinstance(repr(pref), str)

    def test_user_value_and_prompt_repr(self):
        from app.models.user_value_selection import UserValueSelection
        from app.models.value_prompt import ValuePrompt

        selection = UserValueSelection()
        selection.user_id = "user-1"
        selection.value_id = "value-1"
        assert isinstance(repr(selection), str)

        prompt = ValuePrompt()
        prompt.id = "prompt-1"
        prompt.prompt_text = "What matters most?"
        assert isinstance(repr(prompt), str)

    def test_task_completion_repr_and_status_helpers(self):
        from app.models.task_completion import TaskCompletion

        completion = TaskCompletion()
        completion.task_id = "task-1"
        completion.status = "skipped"
        assert isinstance(repr(completion), str)
        assert completion.is_skipped is True
        assert completion.is_completed is False

    def test_dependency_model_reprs(self):
        from app.models.dependency import (
            DependencyResolution,
            DependencyRule,
            DependencyStateCache,
        )

        rule = DependencyRule()
        rule.id = "rule-123456789"
        rule.strength = "hard"
        rule.upstream_task_id = "up-1"
        rule.downstream_task_id = "down-1"
        assert isinstance(repr(rule), str)

        resolution = DependencyResolution()
        resolution.dependency_rule_id = "rule-123456789"
        resolution.resolution_source = "manual"
        assert isinstance(repr(resolution), str)

        cache = DependencyStateCache()
        cache.task_id = "task-1"
        cache.readiness_state = "ready"
        assert isinstance(repr(cache), str)
