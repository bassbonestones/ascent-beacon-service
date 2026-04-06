"""
Helper functions for Tasks API.
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Task, Goal
from app.schemas.tasks import TaskResponse, GoalInfo


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
    return task


async def get_goal_for_task_or_404(
    db: AsyncSession, goal_id: str, user_id: str
) -> Goal:
    """Get a goal by ID for task creation, ensuring it belongs to the user."""
    stmt = select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    result = await db.execute(stmt)
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


def task_to_response(
    task: Task, 
    completed_for_today: bool = False,
    completions_today: int = 0,
    completed_times_today: list[str] | None = None,
) -> TaskResponse:
    """Convert Task model to response schema.
    
    Args:
        task: The Task model instance
        completed_for_today: For recurring tasks, whether it's been completed today
        completions_today: For recurring tasks with multiple daily occurrences,
                          how many have been completed today
        completed_times_today: For interval/specific_times modes, the actual 
                              ISO datetime strings of completions today
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
        scheduled_at=task.scheduled_at,
        scheduling_mode=task.scheduling_mode,
        is_recurring=task.is_recurring,
        recurrence_rule=task.recurrence_rule,
        notify_before_minutes=task.notify_before_minutes,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        is_lightning=task.is_lightning,
        goal=goal_info,
        completed_for_today=completed_for_today if task.is_recurring else False,
        completions_today=completions_today if task.is_recurring else 0,
        completed_times_today=completed_times_today or [] if task.is_recurring else [],
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
    task_stmt = select(Task).where(Task.goal_id == goal_id)
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
