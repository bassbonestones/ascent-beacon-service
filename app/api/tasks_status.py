"""
Task status change endpoints.

Handles completing, skipping, and reopening tasks.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.time import utc_now
from app.models import Task, TaskCompletion
from app.schemas.tasks import (
    TaskResponse,
    CompleteTaskRequest,
    SkipTaskRequest,
)
from app.api.helpers.task_helpers import (
    get_task_or_404,
    task_to_response,
    update_goal_progress,
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
    """Mark a task as completed.
    
    For recurring tasks:
    - Creates a TaskCompletion record with status 'completed'
    - Task remains pending (it will recur)
    
    For one-time tasks:
    - Sets task status to 'completed'
    """
    task = await get_task_or_404(db, task_id, user.id)
    
    if task.is_recurring:
        # For recurring tasks, create a completion record
        completion = TaskCompletion(
            task_id=task.id,
            status="completed",
            scheduled_for=request.scheduled_for,
            completed_at=utc_now(),
        )
        db.add(completion)
        # Task stays pending (it recurs)
    else:
        # For one-time tasks, update the task status
        if task.status == "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task is already completed",
            )
        
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
    """Skip a task (does not count as completed).
    
    For recurring tasks:
    - Creates a TaskCompletion record with status 'skipped'
    - Task remains pending (it will recur)
    
    For one-time tasks:
    - Sets task status to 'skipped'
    """
    task = await get_task_or_404(db, task_id, user.id)
    
    if task.is_recurring:
        # For recurring tasks, create a completion record
        completion = TaskCompletion(
            task_id=task.id,
            status="skipped",
            skip_reason=request.reason,
            scheduled_for=request.scheduled_for,
            completed_at=utc_now(),
        )
        db.add(completion)
        # Task stays pending (it recurs)
    else:
        # For one-time tasks, update the task status
        if task.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can only skip pending tasks",
            )
        
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
    """Reopen a completed or skipped task."""
    task = await get_task_or_404(db, task_id, user.id)
    
    if task.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task is already pending",
        )
    
    task.status = "pending"
    task.completed_at = None
    task.updated_at = utc_now()
    
    # Update goal progress
    await update_goal_progress(db, task.goal_id)
    
    await db.commit()
    task = await get_task_or_404(db, task.id, user.id)
    return task_to_response(task)
