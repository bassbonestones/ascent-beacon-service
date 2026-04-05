"""
Tasks API endpoints.

Provides CRUD operations for tasks linked to goals.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_, or_
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
    stmt = (
        select(Task)
        .options(selectinload(Task.goal))
        .where(Task.user_id == user.id)
        .order_by(Task.scheduled_at.asc().nullslast(), Task.created_at.desc())
    )
    
    if goal_id:
        stmt = stmt.where(Task.goal_id == goal_id)
    
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)
    elif not include_completed:
        stmt = stmt.where(Task.status != "completed")
    
    if scheduled_after:
        from datetime import datetime
        try:
            after_dt = datetime.fromisoformat(scheduled_after.replace("Z", "+00:00"))
            stmt = stmt.where(Task.scheduled_at >= after_dt)
        except ValueError:
            pass
    
    if scheduled_before:
        from datetime import datetime
        try:
            before_dt = datetime.fromisoformat(scheduled_before.replace("Z", "+00:00"))
            stmt = stmt.where(Task.scheduled_at <= before_dt)
        except ValueError:
            pass
    
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())
    
    # Count stats
    pending_count = sum(1 for t in tasks if t.status == "pending")
    completed_count = sum(1 for t in tasks if t.status == "completed")
    
    return TaskListResponse(
        tasks=[task_to_response(t) for t in tasks],
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
    return task_to_response(task)


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
    return task_to_response(task)


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
