"""
Tasks Status API endpoints.

Provides status change operations: complete, skip, and reopen tasks.
"""
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.time import utc_now
from app.models.task_completion import TaskCompletion
from app.schemas.tasks import (
    CompleteTaskRequest,
    ReopenTaskRequest,
    SkipTaskRequest,
    TaskResponse,
)
from app.api.helpers.task_helpers import (
    get_task_or_404,
    task_to_response,
    update_goal_progress,
    assign_sort_order_for_anytime,
    clear_sort_order_for_completed,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


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
    For anytime tasks: also clears sort_order and shifts others down.
    """
    task = await get_task_or_404(db, task_id, user.id)
    
    if task.is_recurring:
        # Record completion for this occurrence
        completion = TaskCompletion(
            task_id=task.id,
            status="completed",
            completed_at=utc_now(),
            scheduled_for=request.scheduled_for,
            local_date=request.local_date,
        )
        db.add(completion)
        # Task stays pending for next occurrence
    else:
        # One-time task: check if already completed
        if task.status == "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task is already completed",
            )
        # One-time task: mark as completed
        task.status = "completed"
        task.completed_at = utc_now()
        task.updated_at = utc_now()
        
        # Phase 4e: Clear sort_order for completed anytime tasks
        await clear_sort_order_for_completed(db, task)
    
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
    For anytime tasks: also clears sort_order and shifts others down.
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
            local_date=request.local_date,
        )
        db.add(completion)
        # Task stays pending for next occurrence
    else:
        # One-time task: check if pending before skipping
        if task.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only skip pending tasks",
            )
        # One-time task: mark as skipped
        task.status = "skipped"
        task.skip_reason = request.reason
        task.updated_at = utc_now()
        
        # Phase 4e: Clear sort_order for skipped anytime tasks
        await clear_sort_order_for_completed(db, task)
    
    await db.commit()
    task = await get_task_or_404(db, task.id, user.id)
    # For recurring tasks, mark as skipped for today
    return task_to_response(task, skipped_for_today=task.is_recurring)


@router.post(
    "/{task_id}/reopen",
    response_model=TaskResponse,
    summary="Reopen task",
)
async def reopen_task(
    task_id: str,
    request: ReopenTaskRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    """
    Reopen a completed or skipped task.
    
    For recurring tasks: deletes the completion record for the specified time slot.
    For one-time tasks: sets status back to pending.
    """
    task = await get_task_or_404(db, task_id, user.id)
    
    if task.is_recurring:
        # For recurring tasks, delete the completion for the specified time
        if not request.scheduled_for:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scheduled_for is required to reopen a recurring task occurrence",
            )
        
        # Determine window size based on whether task has a specific scheduled time
        # For tasks without scheduled_at (anytime tasks), use the whole day
        # For tasks with scheduled_at, use a 2-minute window around the time
        target_time = request.scheduled_for
        if task.scheduled_at is None:
            # No specific time: use day-wide window
            window_start = target_time.replace(hour=0, minute=0, second=0, microsecond=0)
            window_end = target_time.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            # Specific time: use a narrow window (within same minute)
            target_time = target_time.replace(second=0, microsecond=0)
            window_start = target_time - timedelta(minutes=1)
            window_end = target_time + timedelta(minutes=1)
        
        # Find and delete the completion record within the window
        completion_stmt = (
            select(TaskCompletion)
            .where(
                and_(
                    TaskCompletion.task_id == task.id,
                    TaskCompletion.scheduled_for >= window_start,
                    TaskCompletion.scheduled_for <= window_end,
                )
            )
            .order_by(TaskCompletion.completed_at.desc())
            .limit(1)
        )
        result = await db.execute(completion_stmt)
        completion = result.scalar_one_or_none()
        
        if not completion:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No completion found for that time slot",
            )
        
        await db.delete(completion)
        await db.commit()
        
        # Return updated task (still pending, but with updated completion counts)
        task = await get_task_or_404(db, task.id, user.id)
        return task_to_response(task)
    
    # For one-time tasks: reopen as before
    if task.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task is already pending",
        )
    
    task.status = "pending"
    task.completed_at = None
    task.skip_reason = None
    task.updated_at = utc_now()
    
    # Phase 4e: Re-assign sort_order for reopened anytime tasks (at the bottom)
    await assign_sort_order_for_anytime(db, task)
    
    # Update goal progress
    await update_goal_progress(db, task.goal_id)
    
    await db.commit()
    task = await get_task_or_404(db, task.id, user.id)
    return task_to_response(task)
