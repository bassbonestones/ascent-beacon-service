"""
Tasks API endpoints.

Provides CRUD operations for tasks linked to goals.
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.time import utc_now
from app.models import Task
from app.models.task_completion import TaskCompletion
from app.schemas.tasks import (
    CompleteTaskRequest,
    CreateTaskRequest,
    SkipTaskRequest,
    TaskListResponse,
    TaskResponse,
    UpdateTaskRequest,
)
from app.api.helpers.task_helpers import (
    get_task_or_404,
    get_goal_for_task_or_404,
    task_to_response,
    update_goal_progress,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create task",
)
async def create_task(
    request: CreateTaskRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """Create a new task, optionally linked to a goal."""
    # Validate goal exists and belongs to user (if provided)
    if request.goal_id:
        await get_goal_for_task_or_404(db, request.goal_id, user.id)
    
    # Validate scheduling_mode is set for recurring tasks with times
    if request.is_recurring and request.scheduled_at and not request.scheduling_mode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scheduling_mode is required for recurring tasks with scheduled times",
        )
    
    task = Task(
        user_id=user.id,
        goal_id=request.goal_id,
        title=request.title,
        description=request.description,
        duration_minutes=request.duration_minutes,
        scheduled_at=request.scheduled_at,
        is_recurring=request.is_recurring,
        recurrence_rule=request.recurrence_rule,
        scheduling_mode=request.scheduling_mode,
        notify_before_minutes=request.notify_before_minutes,
        status="pending",
    )
    db.add(task)
    await db.flush()
    
    # Update goal progress (if linked to a goal)
    if request.goal_id:
        await update_goal_progress(db, request.goal_id)
    
    await db.commit()
    
    # Reload with goal relationship
    task = await get_task_or_404(db, task.id, user.id)
    return task_to_response(task)


@router.get("", response_model=TaskListResponse, summary="List tasks")
async def list_tasks(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    goal_id: str | None = Query(default=None, description="Filter by goal"),
    status_filter: str | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
    include_completed: bool = Query(
        default=False, description="Include completed tasks"
    ),
    scheduled_after: str | None = Query(
        default=None, description="Tasks scheduled after this datetime (ISO)"
    ),
    scheduled_before: str | None = Query(
        default=None, description="Tasks scheduled before this datetime (ISO)"
    ),
) -> TaskListResponse:
    """Get all tasks for the current user, with optional filters."""
    # Get today's date range for recurring task completion check
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1) - timedelta(microseconds=1)
    
    # First, get IDs of recurring tasks completed or skipped today
    completed_today_subquery = (
        select(TaskCompletion.task_id)
        .join(Task, Task.id == TaskCompletion.task_id)
        .where(
            and_(
                Task.user_id == user.id,
                Task.is_recurring == True,  # noqa: E712
                TaskCompletion.status.in_(["completed", "skipped"]),
                TaskCompletion.scheduled_for >= start_of_day,
                TaskCompletion.scheduled_for <= end_of_day,
            )
        )
    )
    
    stmt = (
        select(Task)
        .options(selectinload(Task.goal))
        .where(Task.user_id == user.id)
        .order_by(Task.scheduled_at.asc().nullslast(), Task.created_at.desc())
    )
    
    if goal_id:
        stmt = stmt.where(Task.goal_id == goal_id)
    
    if status_filter == "completed":
        # Include: non-recurring completed tasks OR recurring tasks completed today
        stmt = stmt.where(
            or_(
                and_(Task.is_recurring == False, Task.status == "completed"),  # noqa: E712
                Task.id.in_(completed_today_subquery),
            )
        )
    elif status_filter == "pending":
        # Include: all pending tasks
        # For recurring tasks with multiple daily occurrences, the frontend
        # tracks completion via completions_today and generates virtual occurrences
        stmt = stmt.where(Task.status == "pending")
    elif status_filter:
        stmt = stmt.where(Task.status == status_filter)
    elif not include_completed:
        stmt = stmt.where(Task.status != "completed")
    
    if scheduled_after:
        try:
            after_dt = datetime.fromisoformat(scheduled_after.replace("Z", "+00:00"))
            stmt = stmt.where(Task.scheduled_at >= after_dt)
        except ValueError:
            pass
    
    if scheduled_before:
        try:
            before_dt = datetime.fromisoformat(scheduled_before.replace("Z", "+00:00"))
            stmt = stmt.where(Task.scheduled_at <= before_dt)
        except ValueError:
            pass
    
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())
    
    # Get today's completion counts for recurring tasks
    # This tracks how many times each recurring task was completed/skipped today
    recurring_task_ids = [t.id for t in tasks if t.is_recurring]
    completions_today_count: dict[str, int] = {}
    
    if recurring_task_ids:
        completion_stmt = (
            select(TaskCompletion.task_id, func.count(TaskCompletion.id).label("count"))
            .where(
                and_(
                    TaskCompletion.task_id.in_(recurring_task_ids),
                    TaskCompletion.status.in_(["completed", "skipped"]),
                    TaskCompletion.scheduled_for >= start_of_day,
                    TaskCompletion.scheduled_for <= end_of_day,
                )
            )
            .group_by(TaskCompletion.task_id)
        )
        completion_result = await db.execute(completion_stmt)
        completions_today_count = {row[0]: row[1] for row in completion_result.fetchall()}
    
    # Count stats
    pending_count = sum(1 for t in tasks if t.status == "pending")
    completed_count = sum(1 for t in tasks if t.status == "completed")
    
    return TaskListResponse(
        tasks=[
            task_to_response(
                t, 
                completed_for_today=t.id in completions_today_count,
                completions_today=completions_today_count.get(t.id, 0),
            )
            for t in tasks
        ],
        total=len(tasks),
        pending_count=pending_count,
        completed_count=completed_count,
    )


@router.get("/{task_id}", response_model=TaskResponse, summary="Get task")
async def get_task(
    task_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """Get a task by ID."""
    task = await get_task_or_404(db, task_id, user.id)
    return task_to_response(task)


@router.patch("/{task_id}", response_model=TaskResponse, summary="Update task")
async def update_task(
    task_id: str,
    request: UpdateTaskRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """Update a task's fields."""
    task = await get_task_or_404(db, task_id, user.id)
    old_goal_id = task.goal_id
    
    # Handle goal change
    if request.goal_id is not None and request.goal_id != task.goal_id:
        await get_goal_for_task_or_404(db, request.goal_id, user.id)
        task.goal_id = request.goal_id
    
    if request.title is not None:
        task.title = request.title
    if request.description is not None:
        task.description = request.description
    if request.duration_minutes is not None:
        task.duration_minutes = request.duration_minutes
    if request.scheduled_at is not None:
        task.scheduled_at = request.scheduled_at
    if request.notify_before_minutes is not None:
        task.notify_before_minutes = request.notify_before_minutes
    
    # Phase 4b: Recurrence fields
    if request.is_recurring is not None:
        task.is_recurring = request.is_recurring
    if request.recurrence_rule is not None:
        task.recurrence_rule = request.recurrence_rule
    if request.scheduling_mode is not None:
        task.scheduling_mode = request.scheduling_mode
    
    task.updated_at = utc_now()
    
    # Update goal progress for both old and new goals
    await update_goal_progress(db, task.goal_id)
    if old_goal_id != task.goal_id:
        await update_goal_progress(db, old_goal_id)
    
    await db.commit()
    task = await get_task_or_404(db, task.id, user.id)
    return task_to_response(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete task",
)
async def delete_task(
    task_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a task."""
    task = await get_task_or_404(db, task_id, user.id)
    goal_id = task.goal_id
    
    await db.delete(task)
    
    # Update goal progress
    await update_goal_progress(db, goal_id)
    
    await db.commit()


@router.post(
    "/{task_id}/complete",
    response_model=TaskResponse,
    summary="Complete task",
)
async def complete_task(
    task_id: str,
    request: CompleteTaskRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """
    Mark a task as complete.
    
    For recurring tasks: records a completion but keeps task pending.
    For one-time tasks: sets status to 'completed'.
    """
    task = await get_task_or_404(db, task_id, user.id)
    
    if task.is_recurring:
        # Record completion for this occurrence
        completion = TaskCompletion(
            task_id=task.id,
            status="completed",
            completed_at=utc_now(),
            scheduled_for=request.scheduled_for,
        )
        db.add(completion)
        # Task stays pending for next occurrence
    else:
        # One-time task: mark as completed
        task.status = "completed"
        task.completed_at = utc_now()
        task.updated_at = utc_now()
    
    # Update goal progress
    await update_goal_progress(db, task.goal_id)
    
    await db.commit()
    task = await get_task_or_404(db, task.id, user.id)
    # For recurring tasks, we just completed it for today
    return task_to_response(task, completed_for_today=task.is_recurring)


@router.post(
    "/{task_id}/skip",
    response_model=TaskResponse,
    summary="Skip task",
)
async def skip_task(
    task_id: str,
    request: SkipTaskRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """
    Skip a task occurrence.
    
    For recurring tasks: records a skip but keeps task pending.
    For one-time tasks: sets status to 'skipped'.
    """
    task = await get_task_or_404(db, task_id, user.id)
    
    if task.is_recurring:
        # Record skip for this occurrence
        completion = TaskCompletion(
            task_id=task.id,
            status="skipped",
            skip_reason=request.reason,
            completed_at=utc_now(),
            scheduled_for=request.scheduled_for,
        )
        db.add(completion)
        # Task stays pending for next occurrence
    else:
        # One-time task: mark as skipped
        task.status = "skipped"
        task.skip_reason = request.reason
        task.updated_at = utc_now()
    
    await db.commit()
    task = await get_task_or_404(db, task.id, user.id)
    # For recurring tasks, skip also counts as "done for today"
    return task_to_response(task, completed_for_today=task.is_recurring)


@router.post(
    "/{task_id}/reopen",
    response_model=TaskResponse,
    summary="Reopen task",
)
async def reopen_task(
    task_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """
    Reopen a completed or skipped task.
    
    Only applies to one-time tasks. Recurring tasks stay pending.
    """
    task = await get_task_or_404(db, task_id, user.id)
    
    if task.is_recurring:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reopen recurring tasks - they remain pending",
        )
    
    if task.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task is already pending",
        )
    
    task.status = "pending"
    task.completed_at = None
    task.skip_reason = None
    task.updated_at = utc_now()
    
    # Update goal progress
    await update_goal_progress(db, task.goal_id)
    
    await db.commit()
    task = await get_task_or_404(db, task.id, user.id)
    return task_to_response(task)


# ============================================================================
# Time Machine Endpoints
# ============================================================================


@router.delete(
    "/completions/future",
    summary="Delete future completions",
)
async def delete_future_completions(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    after_date: str | None = Query(
        None,
        description="Delete completions after this date (YYYY-MM-DD). Defaults to today if not provided.",
    ),
) -> dict[str, int]:
    """
    Delete all task completions dated after the specified date.
    
    Used by the Time Machine feature to:
    - Reset to present (delete all future completions)
    - Revert to a specific date (delete completions after that date only)
    
    Returns the count of deleted records.
    """
    from datetime import date, datetime
    from sqlalchemy import delete, func
    
    # Parse the after_date or default to today
    if after_date:
        try:
            cutoff_date = datetime.strptime(after_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD.",
            )
    else:
        cutoff_date = date.today()
    
    # First count how many will be deleted
    count_stmt = select(func.count()).select_from(TaskCompletion).where(
        and_(
            TaskCompletion.task_id.in_(
                select(Task.id).where(Task.user_id == user.id)
            ),
            func.date(TaskCompletion.scheduled_for) > cutoff_date
        )
    )
    result = await db.execute(count_stmt)
    deleted_count = result.scalar() or 0
    
    # Delete the future completions
    if deleted_count > 0:
        delete_stmt = delete(TaskCompletion).where(
            and_(
                TaskCompletion.task_id.in_(
                    select(Task.id).where(Task.user_id == user.id)
                ),
                func.date(TaskCompletion.scheduled_for) > cutoff_date
            )
        )
        await db.execute(delete_stmt)
        await db.commit()
    
    return {"deleted_count": deleted_count}
