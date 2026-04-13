"""
Tasks views API endpoints.

Phase 4b: Today view, Range view, and completions endpoints.
"""
from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.models import Task, TaskCompletion
from app.schemas.tasks import (
    TodayTasksResponse,
    TaskRangeRequest,
    TaskRangeResponse,
    TaskCompletionResponse,
    TaskCompletionListResponse,
)
from app.api.helpers.task_helpers import (
    get_task_or_404,
    task_to_response,
)
from app.record_state import ACTIVE

router = APIRouter(prefix="/tasks/view", tags=["tasks-views"])


@router.get("/today", response_model=TodayTasksResponse, summary="Today's tasks")
async def get_today_tasks(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    timezone: str = Query(default="UTC", description="User's timezone for 'today' calculation"),
    include_completed: bool = Query(default=False, description="Include completed tasks"),
) -> TodayTasksResponse:
    """Get today's tasks for the current user.
    
    Returns:
    - One-time tasks scheduled for today
    - Recurring tasks that have an occurrence today
    - Overdue tasks from previous days
    """
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    
    now = datetime.now(tz)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1) - timedelta(microseconds=1)
    
    # Build query for today's tasks
    stmt = (
        select(Task)
        .options(selectinload(Task.goal))
        .where(Task.user_id == user.id, Task.record_state == ACTIVE)
        .where(
            or_(
                # One-time tasks scheduled for today
                and_(
                    Task.is_recurring == False,  # noqa: E712
                    Task.scheduled_at >= start_of_day,
                    Task.scheduled_at <= end_of_day,
                ),
                # Overdue one-time tasks
                and_(
                    Task.is_recurring == False,  # noqa: E712
                    Task.status == "pending",
                    Task.scheduled_at < start_of_day,
                ),
                # Recurring tasks (we'll filter occurrences in Python)
                Task.is_recurring == True,  # noqa: E712
                # Tasks without schedule (always show)
                Task.scheduled_at.is_(None),
            )
        )
        .order_by(Task.scheduled_at.asc().nullslast(), Task.created_at.desc())
    )
    
    if not include_completed:
        stmt = stmt.where(Task.status != "completed")
    
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())
    
    # Count stats
    pending_count = sum(1 for t in tasks if t.status == "pending")
    start_of_day_utc = start_of_day.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    overdue_count = sum(
        1 for t in tasks 
        if t.status == "pending" 
        and t.scheduled_at 
        and t.scheduled_at < start_of_day_utc
    )
    
    # Get today's completions count
    completed_stmt = (
        select(func.count())
        .select_from(Task)
        .where(Task.user_id == user.id)
        .where(Task.status == "completed")
        .where(Task.completed_at >= start_of_day)
        .where(Task.completed_at <= end_of_day)
    )
    completed_result = await db.execute(completed_stmt)
    completed_today_count = completed_result.scalar() or 0
    
    return TodayTasksResponse(
        tasks=[task_to_response(t) for t in tasks],
        pending_count=pending_count,
        completed_today_count=completed_today_count,
        overdue_count=overdue_count,
    )


@router.post("/range", response_model=TaskRangeResponse, summary="Tasks in range")
async def get_tasks_in_range(
    request: TaskRangeRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskRangeResponse:
    """Get tasks within a date range (for 'All' view with pagination).
    
    Loads a few days at a time with pagination support.
    """
    stmt = (
        select(Task)
        .options(selectinload(Task.goal))
        .where(Task.user_id == user.id, Task.record_state == ACTIVE)
        .where(
            or_(
                # Tasks with scheduled times in range
                and_(
                    Task.scheduled_at >= request.start_date,
                    Task.scheduled_at <= request.end_date,
                ),
                # Tasks without schedule created in range
                and_(
                    Task.scheduled_at.is_(None),
                    Task.created_at >= request.start_date,
                    Task.created_at <= request.end_date,
                ),
            )
        )
        .order_by(Task.scheduled_at.asc().nullslast(), Task.created_at.desc())
    )
    
    if not request.include_completed:
        stmt = stmt.where(Task.status != "completed")
    
    # Get total count
    count_stmt = (
        select(func.count())
        .select_from(stmt.subquery())
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0
    
    # Apply pagination
    stmt = stmt.offset(request.offset).limit(request.limit)
    
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())
    
    has_more = (request.offset + len(tasks)) < total
    
    return TaskRangeResponse(
        tasks=[task_to_response(t) for t in tasks],
        total=total,
        has_more=has_more,
        start_date=request.start_date,
        end_date=request.end_date,
    )


# ============================================================================
# Task Completions (for recurring tasks)
# ============================================================================

completions_router = APIRouter(prefix="/tasks", tags=["tasks"])


@completions_router.get(
    "/{task_id}/completions",
    response_model=TaskCompletionListResponse,
    summary="Get task completions",
)
async def get_task_completions(
    task_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TaskCompletionListResponse:
    """Get completion history for a recurring task."""
    task = await get_task_or_404(db, task_id, user.id)
    
    if not task.is_recurring:
        return TaskCompletionListResponse(
            completions=[],
            total=0,
            completed_count=0,
            skipped_count=0,
        )
    
    # Get completions
    stmt = (
        select(TaskCompletion)
        .where(TaskCompletion.task_id == task_id)
        .order_by(TaskCompletion.completed_at.desc())
    )
    
    result = await db.execute(stmt)
    completions = list(result.scalars().all())
    
    total = len(completions)
    completed_count = sum(1 for c in completions if c.status == "completed")
    skipped_count = sum(1 for c in completions if c.status == "skipped")
    
    # Apply pagination
    paginated = completions[offset:offset + limit]
    
    return TaskCompletionListResponse(
        completions=[
            TaskCompletionResponse.model_validate(c) for c in paginated
        ],
        total=total,
        completed_count=completed_count,
        skipped_count=skipped_count,
    )
