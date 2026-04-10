"""
Tasks CRUD API endpoints.

Provides Create, Read, Update, Delete operations for tasks linked to goals.
Note: list_tasks is in tasks_list.py due to completion tracking complexity.
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.time import utc_now
from app.models import Task
from app.schemas.tasks import (
    CreateTaskRequest,
    TaskResponse,
    UpdateTaskRequest,
)
from app.api.helpers.task_helpers import (
    get_task_or_404,
    get_goal_for_task_or_404,
    task_to_response,
    update_goal_progress,
    assign_sort_order_for_anytime,
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
    
    # Phase 4e: Anytime tasks cannot be recurring (they need schedules for occurrences)
    if request.scheduling_mode == "anytime" and request.is_recurring:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anytime tasks cannot be recurring",
        )
    
    # Phase 4g: Recurring tasks must have recurrence_behavior set
    if request.is_recurring and not request.recurrence_behavior:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="recurrence_behavior is required for recurring tasks",
        )
    
    # Phase 4g: Non-recurring tasks should not have recurrence_behavior
    if not request.is_recurring and request.recurrence_behavior:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="recurrence_behavior should only be set for recurring tasks",
        )
    
    # Determine scheduling_mode if not explicitly provided
    scheduling_mode = request.scheduling_mode
    if scheduling_mode is None:
        if request.scheduled_date and not request.scheduled_at:
            scheduling_mode = "date_only"
    
    task = Task(
        user_id=user.id,
        goal_id=request.goal_id,
        title=request.title,
        description=request.description,
        duration_minutes=request.duration_minutes,
        scheduled_date=request.scheduled_date,
        scheduled_at=request.scheduled_at,
        is_recurring=request.is_recurring,
        recurrence_rule=request.recurrence_rule,
        scheduling_mode=scheduling_mode,
        recurrence_behavior=request.recurrence_behavior,
        notify_before_minutes=request.notify_before_minutes,
        status="pending",
    )
    db.add(task)
    await db.flush()
    
    # Phase 4e: Assign sort_order for anytime tasks (at the bottom of the list)
    await assign_sort_order_for_anytime(db, task)
    
    # Update goal progress (if linked to a goal)
    if request.goal_id:
        await update_goal_progress(db, request.goal_id)
    
    await db.commit()
    
    # Reload with goal relationship
    task = await get_task_or_404(db, task.id, user.id)
    return task_to_response(task)


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
    
    # Use exclude_unset to detect what was explicitly sent
    update_data = request.model_dump(exclude_unset=True)
    
    if "title" in update_data:
        task.title = request.title  # type: ignore[assignment]
    if "description" in update_data:
        task.description = request.description
    if "duration_minutes" in update_data:
        task.duration_minutes = request.duration_minutes  # type: ignore[assignment]
    if "notify_before_minutes" in update_data:
        task.notify_before_minutes = request.notify_before_minutes
    
    # Handle scheduling fields - scheduled_date and scheduled_at
    # When one is set, the other should typically be cleared
    if "scheduled_date" in update_data:
        task.scheduled_date = request.scheduled_date
    if "scheduled_at" in update_data:
        task.scheduled_at = request.scheduled_at
    
    # Auto-determine scheduling_mode if scheduling fields changed
    if "scheduled_date" in update_data or "scheduled_at" in update_data:
        if task.scheduled_date and not task.scheduled_at:
            task.scheduling_mode = "date_only"
        elif task.scheduled_at and not task.scheduled_date:
            # Keep existing mode if already set, otherwise don't set
            if not task.scheduling_mode or task.scheduling_mode == "date_only":
                task.scheduling_mode = None  # Let it be inferred
    
    # Phase 4b: Recurrence fields
    if "is_recurring" in update_data:
        task.is_recurring = request.is_recurring  # type: ignore[assignment]
    if "recurrence_rule" in update_data:
        task.recurrence_rule = request.recurrence_rule
    if "scheduling_mode" in update_data and request.scheduling_mode is not None:
        task.scheduling_mode = request.scheduling_mode
    if "recurrence_behavior" in update_data:
        task.recurrence_behavior = request.recurrence_behavior
    
    # Phase 4g: Validate recurrence_behavior consistency after all updates
    if task.is_recurring and not task.recurrence_behavior:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="recurrence_behavior is required for recurring tasks",
        )
    if not task.is_recurring and task.recurrence_behavior:
        # Clear recurrence_behavior if task is no longer recurring
        task.recurrence_behavior = None
    
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
