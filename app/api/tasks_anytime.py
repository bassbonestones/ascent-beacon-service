"""
Anytime Tasks API endpoints.

Phase 4e: Provides backlog/anytime task management operations.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.time import utc_now
from app.models import Task
from app.schemas.tasks import (
    AnytimeTasksResponse,
    ReorderTaskRequest,
    ReorderTaskResponse,
)
from app.api.helpers.task_helpers import (
    get_task_or_404,
    task_to_response,
    reorder_anytime_task,
)
from app.record_state import ACTIVE

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get(
    "/view/anytime",
    response_model=AnytimeTasksResponse,
    summary="List anytime tasks",
)
async def list_anytime_tasks(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_completed: bool = Query(
        default=False,
        description="Include completed anytime tasks",
    ),
) -> AnytimeTasksResponse:
    """
    Get all anytime tasks (backlog) for the current user.
    
    Anytime tasks are:
    - Not scheduled to a specific date/time
    - Never become overdue
    - User-ordered via sort_order field
    
    Returns pending anytime tasks sorted by sort_order (ascending).
    """
    stmt = (
        select(Task)
        .options(selectinload(Task.goal))
        .where(
            Task.user_id == user.id,
            Task.scheduling_mode == "anytime",
            Task.record_state == ACTIVE,
        )
    )
    
    if not include_completed:
        stmt = stmt.where(Task.status == "pending")
    
    # Sort by sort_order (pending tasks), then by updated_at for completed
    stmt = stmt.order_by(
        Task.sort_order.asc().nullslast(),
        Task.updated_at.desc(),
    )
    
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())
    
    return AnytimeTasksResponse(
        tasks=[task_to_response(t) for t in tasks],
        total=len(tasks),
    )


@router.patch(
    "/{task_id}/reorder",
    response_model=ReorderTaskResponse,
    summary="Reorder anytime task",
)
async def reorder_task(
    task_id: str,
    request: ReorderTaskRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReorderTaskResponse:
    """
    Reorder an anytime task to a new position.
    
    new_position is 1-indexed (1 = top of list).
    Other tasks shift to accommodate the move.
    
    Only works for anytime tasks that are pending (have a sort_order).
    """
    task = await get_task_or_404(db, task_id, user.id)
    
    await reorder_anytime_task(db, task, request.new_position)
    
    task.updated_at = utc_now()
    await db.commit()
    
    task = await get_task_or_404(db, task.id, user.id)
    return ReorderTaskResponse(task=task_to_response(task))
