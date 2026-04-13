"""
Helper functions for Tasks API.
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Task, Goal
from app.models.dependency import DependencyRule
from app.record_state import ACTIVE, DELETED
from app.schemas.tasks import GoalInfo, TaskDependencySummary, TaskResponse


def _task_str_field(task: object, name: str, default: str | None) -> str | None:
    v = getattr(task, name, default)
    if isinstance(v, str):
        return v
    return default


def _task_dt_field(task: object, name: str) -> datetime | None:
    if not hasattr(task, name):
        return None
    v = getattr(task, name)
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    return None


async def get_task_or_404(
    db: AsyncSession, task_id: str, user_id: str
) -> Task:
    """Get a task by ID, ensuring it belongs to the user."""
    stmt = (
        select(Task)
        .options(selectinload(Task.goal))
        .where(Task.id == task_id, Task.user_id == user_id)
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if (_task_str_field(task, "record_state", "active") or "active") == DELETED:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def get_active_task_or_404(
    db: AsyncSession, task_id: str, user_id: str
) -> Task:
    """Task must exist, belong to user, and have ``record_state == active``."""
    task = await get_task_or_404(db, task_id, user_id)
    if (_task_str_field(task, "record_state", "active") or "active") != ACTIVE:
        raise HTTPException(
            status_code=409,
            detail="Task is not active",
        )
    return task


async def get_goal_for_task_or_404(
    db: AsyncSession, goal_id: str, user_id: str
) -> Goal:
    """Get a goal by ID for task creation, ensuring it belongs to the user."""
    from app.record_state import ACTIVE

    stmt = select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    result = await db.execute(stmt)
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if (_task_str_field(goal, "record_state", "active") or "active") != ACTIVE:
        raise HTTPException(
            status_code=409,
            detail="Goal is not active",
        )
    return goal


async def task_has_dependency_edges(db: AsyncSession, task_id: str) -> bool:
    """True if any dependency rule references this task."""
    r = await db.execute(
        select(func.count())
        .select_from(DependencyRule)
        .where(
            or_(
                DependencyRule.upstream_task_id == task_id,
                DependencyRule.downstream_task_id == task_id,
            )
        )
    )
    n = r.scalar_one()
    return int(n or 0) > 0


def task_to_response(
    task: Task, 
    completed_for_today: bool = False,
    completions_today: int = 0,
    completed_times_today: list[str] | None = None,
    completions_by_date: dict[str, list[str]] | None = None,
    skipped_for_today: bool = False,
    skips_today: int = 0,
    skipped_times_today: list[str] | None = None,
    skips_by_date: dict[str, list[str]] | None = None,
    skip_reason_today: str | None = None,
    skip_reasons_by_date: dict[str, str | None] | None = None,
    dependency_summary: TaskDependencySummary | None = None,
    dependency_summaries_by_local_date: dict[str, dict[str, TaskDependencySummary]]
    | None = None,
) -> TaskResponse:
    """Convert Task model to response schema.
    
    Args:
        task: The Task model instance
        completed_for_today: For recurring tasks, whether it's been completed today
        completions_today: For recurring tasks with multiple daily occurrences,
                          how many have been completed today
        completed_times_today: For interval/specific_times modes, the actual 
                              ISO datetime strings of completions today
        completions_by_date: For recurring tasks, dict mapping date strings (YYYY-MM-DD)
                            to lists of completion timestamps for that date
        skipped_for_today: For recurring tasks, whether it's been skipped today
        skips_today: For recurring tasks, how many skips today
        skipped_times_today: For recurring tasks, the actual skip timestamps
        skips_by_date: For recurring tasks, dict mapping date strings to skip timestamps
        skip_reason_today: For recurring tasks, the skip reason for today
        skip_reasons_by_date: For recurring tasks, skip reasons by date
    """
    goal_info = None
    if task.goal:
        goal_info = GoalInfo(
            id=task.goal.id,
            title=task.goal.title,
            status=task.goal.status,
        )
    
    return TaskResponse(
        id=task.id,
        user_id=task.user_id,
        goal_id=task.goal_id,
        title=task.title,
        description=task.description,
        duration_minutes=task.duration_minutes,
        status=task.status,
        scheduled_date=task.scheduled_date,
        scheduled_at=task.scheduled_at,
        scheduling_mode=task.scheduling_mode,
        is_recurring=task.is_recurring,
        recurrence_rule=task.recurrence_rule,
        recurrence_behavior=task.recurrence_behavior,
        notify_before_minutes=task.notify_before_minutes,
        completed_at=task.completed_at,
        skip_reason=task.skip_reason,
        sort_order=task.sort_order,
        created_at=task.created_at,
        updated_at=task.updated_at,
        is_lightning=task.is_lightning,
        goal=goal_info,
        record_state=_task_str_field(task, "record_state", "active") or "active",
        unaligned_execution_acknowledged_at=_task_dt_field(
            task, "unaligned_execution_acknowledged_at"
        ),
        completed_for_today=completed_for_today if task.is_recurring else False,
        completions_today=completions_today if task.is_recurring else 0,
        completed_times_today=completed_times_today or [] if task.is_recurring else [],
        completions_by_date=completions_by_date or {} if task.is_recurring else {},
        skipped_for_today=skipped_for_today if task.is_recurring else False,
        skips_today=skips_today if task.is_recurring else 0,
        skipped_times_today=skipped_times_today or [] if task.is_recurring else [],
        skips_by_date=skips_by_date or {} if task.is_recurring else {},
        skip_reason_today=skip_reason_today if task.is_recurring else None,
        skip_reasons_by_date=skip_reasons_by_date or {} if task.is_recurring else {},
        dependency_summary=dependency_summary,
        dependency_summaries_by_local_date=dependency_summaries_by_local_date,
    )


async def update_goal_progress(db: AsyncSession, goal_id: str | None) -> None:
    """
    Recalculate goal progress based on tasks.
    
    Progress calculation:
    - For time-based tasks: completed_time / total_time
    - For lightning tasks only: completed_count / total_count
    
    If goal_id is None (task not linked to a goal), do nothing.
    """
    if goal_id is None:
        return
    
    # Get all tasks for this goal
    task_stmt = select(Task).where(
        Task.goal_id == goal_id,
        Task.record_state == ACTIVE,
    )
    result = await db.execute(task_stmt)
    tasks = list(result.scalars().all())
    
    if not tasks:
        # No tasks = has_incomplete_breakdown = true
        goal_stmt = select(Goal).where(Goal.id == goal_id)
        goal_result = await db.execute(goal_stmt)
        goal = goal_result.scalar_one_or_none()
        if goal:
            goal.has_incomplete_breakdown = True
            goal.progress_cached = 0
            goal.total_time_minutes = 0
            goal.completed_time_minutes = 0
        return
    
    # Calculate totals
    total_time = sum(t.duration_minutes for t in tasks)
    completed_time = sum(
        t.duration_minutes for t in tasks if t.status == "completed"
    )
    
    # Calculate progress
    if total_time > 0:
        # Time-based progress
        progress = int((completed_time / total_time) * 100)
    else:
        # All lightning tasks - use count-based progress
        completed_count = sum(1 for t in tasks if t.status == "completed")
        progress = int((completed_count / len(tasks)) * 100)
    
    # Update goal
    goal_stmt = select(Goal).where(Goal.id == goal_id)
    goal_result = await db.execute(goal_stmt)
    goal = goal_result.scalar_one_or_none()
    if goal:
        goal.progress_cached = progress
        goal.total_time_minutes = total_time
        goal.completed_time_minutes = completed_time
        goal.has_incomplete_breakdown = False  # Goal has tasks
        
        # Auto-transition to in_progress when first task is completed
        if goal.status == "not_started" and any(t.status == "completed" for t in tasks):
            goal.status = "in_progress"


# ============================================================================
# Anytime Tasks Helpers (Phase 4e)
# ============================================================================


async def get_max_sort_order(db: AsyncSession, user_id: str) -> int:
    """Get the maximum sort_order for a user's anytime tasks.
    
    Returns 0 if no anytime tasks exist.
    """
    from sqlalchemy import func
    
    stmt = select(func.max(Task.sort_order)).where(
        Task.user_id == user_id,
        Task.scheduling_mode == "anytime",
    )
    result = await db.execute(stmt)
    max_order = result.scalar()
    return max_order if max_order is not None else 0


async def assign_sort_order_for_anytime(db: AsyncSession, task: Task) -> None:
    """Assign sort_order to a new anytime task (at the bottom of the list)."""
    if task.scheduling_mode != "anytime":
        return
    
    max_order = await get_max_sort_order(db, task.user_id)
    task.sort_order = max_order + 1


async def clear_sort_order_for_completed(db: AsyncSession, task: Task) -> None:
    """Clear sort_order when an anytime task is completed.
    
    Also shifts remaining tasks down to fill the gap.
    """
    if task.scheduling_mode != "anytime" or task.sort_order is None:
        return
    
    old_order = task.sort_order
    task.sort_order = None
    
    # Shift other tasks down to fill the gap
    from sqlalchemy import update
    
    stmt = (
        update(Task)
        .where(
            Task.user_id == task.user_id,
            Task.scheduling_mode == "anytime",
            Task.sort_order > old_order,
        )
        .values(sort_order=Task.sort_order - 1)
    )
    await db.execute(stmt)


async def reorder_anytime_task(
    db: AsyncSession, task: Task, new_position: int
) -> None:
    """Reorder an anytime task to a new position.
    
    new_position is 1-indexed (1 = top of list).
    """
    if task.scheduling_mode != "anytime":
        raise HTTPException(
            status_code=400,
            detail="Only anytime tasks can be reordered",
        )
    
    old_order = task.sort_order
    if old_order is None:
        # Task was completed, doesn't have a position
        raise HTTPException(
            status_code=400,
            detail="Cannot reorder a completed anytime task",
        )
    
    # Get current max to validate new_position
    max_order = await get_max_sort_order(db, task.user_id)
    
    # Clamp new_position to valid range
    new_order = max(1, min(new_position, max_order))
    
    if new_order == old_order:
        return  # No change needed
    
    from sqlalchemy import update
    
    if new_order < old_order:
        # Moving up: shift tasks in [new_order, old_order-1] down
        stmt = (
            update(Task)
            .where(
                Task.user_id == task.user_id,
                Task.scheduling_mode == "anytime",
                Task.sort_order >= new_order,
                Task.sort_order < old_order,
            )
            .values(sort_order=Task.sort_order + 1)
        )
        await db.execute(stmt)
    else:
        # Moving down: shift tasks in [old_order+1, new_order] up
        stmt = (
            update(Task)
            .where(
                Task.user_id == task.user_id,
                Task.scheduling_mode == "anytime",
                Task.sort_order > old_order,
                Task.sort_order <= new_order,
            )
            .values(sort_order=Task.sort_order - 1)
        )
        await db.execute(stmt)
    
    task.sort_order = new_order
