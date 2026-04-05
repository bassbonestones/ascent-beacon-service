"""
Task Stats API endpoints.

Provides habit tracking statistics and completion history for tasks.
"""
from datetime import datetime, date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.models import Task
from app.models.task_completion import TaskCompletion
from app.schemas.tasks import (
    TaskStatsResponse,
    TaskStatsPeriod,
    CompletionHistoryResponse,
    DailyCompletionStatus,
)
from app.services.recurrence import get_occurrences_in_range

router = APIRouter(prefix="/tasks", tags=["task-stats"])


async def get_task_or_404(
    db: AsyncSession, task_id: str, user_id: str
) -> Task:
    """Get a task by ID or raise 404."""
    stmt = select(Task).where(
        and_(Task.id == task_id, Task.user_id == user_id)
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return task


def calculate_streak(
    completions: list[TaskCompletion],
    end_date: date,
    expected_dates: set[date],
) -> tuple[int, int]:
    """
    Calculate current and longest streaks.
    
    Returns: (current_streak, longest_streak)
    """
    if not completions or not expected_dates:
        return 0, 0
    
    # Build set of completed dates
    completed_dates = {
        c.completed_at.date() for c in completions if c.status == "completed"
    }
    
    # Sort expected dates
    sorted_dates = sorted(expected_dates)
    
    # Calculate longest streak
    longest = 0
    current = 0
    for d in sorted_dates:
        if d in completed_dates:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    
    # Calculate current streak (consecutive completions ending at most recent expected date <= today)
    current_streak = 0
    for d in reversed(sorted_dates):
        if d > end_date:
            continue
        if d in completed_dates:
            current_streak += 1
        else:
            break
    
    return current_streak, longest


@router.get(
    "/{task_id}/stats",
    response_model=TaskStatsResponse,
    summary="Get task stats",
)
async def get_task_stats(
    task_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    start: datetime = Query(..., description="Start of period (ISO format)"),
    end: datetime = Query(..., description="End of period (ISO format)"),
) -> TaskStatsResponse:
    """
    Get statistics for a task over a time period.
    
    Useful for habit tracking: streaks, completion rates, etc.
    Only meaningful for recurring tasks.
    """
    task = await get_task_or_404(db, task_id, user.id)
    
    # Get completions in range (filter by scheduled_for, fallback to completed_at for legacy)
    # Use COALESCE to handle records where scheduled_for is NULL
    scheduled_or_completed = func.coalesce(
        TaskCompletion.scheduled_for, TaskCompletion.completed_at
    )
    stmt = (
        select(TaskCompletion)
        .where(
            and_(
                TaskCompletion.task_id == task_id,
                scheduled_or_completed >= start,
                scheduled_or_completed <= end,
            )
        )
        .order_by(scheduled_or_completed)
    )
    result = await db.execute(stmt)
    completions = list(result.scalars().all())
    
    # Calculate expected occurrences from RRULE
    if task.is_recurring and task.recurrence_rule:
        occurrences = get_occurrences_in_range(
            task.recurrence_rule,
            start,
            end,
            task.scheduling_mode,
            dtstart=task.scheduled_at,
        )
        expected_dates = {occ.date() for occ in occurrences}
        total_expected = len(occurrences)
    else:
        # Non-recurring task: expected = 1 if scheduled in range
        total_expected = 1
        expected_dates = {task.scheduled_at.date()} if task.scheduled_at else set()
    
    # Count completions and skips
    total_completed = sum(1 for c in completions if c.status == "completed")
    total_skipped = sum(1 for c in completions if c.status == "skipped")
    total_missed = max(0, total_expected - total_completed - total_skipped)
    
    # Completion rate
    completion_rate = total_completed / total_expected if total_expected > 0 else 0.0
    
    # Streaks
    current_streak, longest_streak = calculate_streak(
        completions, end.date(), expected_dates
    )
    
    # Last completed
    completed_completions = [c for c in completions if c.status == "completed"]
    last_completed_at = (
        completed_completions[-1].completed_at if completed_completions else None
    )
    
    return TaskStatsResponse(
        task_id=task_id,
        period=TaskStatsPeriod(start=start, end=end),
        total_expected=total_expected,
        total_completed=total_completed,
        total_skipped=total_skipped,
        total_missed=total_missed,
        completion_rate=round(completion_rate, 3),
        current_streak=current_streak,
        longest_streak=longest_streak,
        last_completed_at=last_completed_at,
    )


@router.get(
    "/{task_id}/history",
    response_model=CompletionHistoryResponse,
    summary="Get completion history",
)
async def get_completion_history(
    task_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    start: datetime = Query(..., description="Start of period (ISO format)"),
    end: datetime = Query(..., description="End of period (ISO format)"),
) -> CompletionHistoryResponse:
    """
    Get day-by-day completion history for calendar visualization.
    
    Each day shows: completed, skipped, missed, or partial (for multi-occurrence days).
    """
    task = await get_task_or_404(db, task_id, user.id)
    
    # Get completions in range (filter by scheduled_for, fallback to completed_at for legacy)
    scheduled_or_completed = func.coalesce(
        TaskCompletion.scheduled_for, TaskCompletion.completed_at
    )
    stmt = (
        select(TaskCompletion)
        .where(
            and_(
                TaskCompletion.task_id == task_id,
                scheduled_or_completed >= start,
                scheduled_or_completed <= end,
            )
        )
        .order_by(scheduled_or_completed)
    )
    result = await db.execute(stmt)
    completions = list(result.scalars().all())
    
    # Calculate expected occurrences from RRULE
    if task.is_recurring and task.recurrence_rule:
        occurrences = get_occurrences_in_range(
            task.recurrence_rule,
            start,
            end,
            task.scheduling_mode,
            dtstart=task.scheduled_at,
        )
        # Convert to dates, keeping count per date for multi-occurrence days
        expected_dates: set[date] = set()
        expected_per_date: dict[date, int] = {}
        for occ in occurrences:
            d = occ.date()
            expected_dates.add(d)
            expected_per_date[d] = expected_per_date.get(d, 0) + 1
    else:
        expected_dates = {task.scheduled_at.date()} if task.scheduled_at else set()
        expected_per_date = {task.scheduled_at.date(): 1} if task.scheduled_at else {}
    
    # Group completions by date (use scheduled_for date, not completed_at)
    completions_by_date: dict[date, list[TaskCompletion]] = {}
    for c in completions:
        d = c.scheduled_for.date() if c.scheduled_for else c.completed_at.date()
        if d not in completions_by_date:
            completions_by_date[d] = []
        completions_by_date[d].append(c)
    
    # Build day-by-day status
    days: list[DailyCompletionStatus] = []
    all_dates = sorted(expected_dates | set(completions_by_date.keys()))
    
    for d in all_dates:
        expected = expected_per_date.get(d, 0)
        day_completions = completions_by_date.get(d, [])
        completed = sum(1 for c in day_completions if c.status == "completed")
        skipped = sum(1 for c in day_completions if c.status == "skipped")
        
        # Determine status
        if expected == 0:
            # Extra completion on non-expected day
            status_str = "completed" if completed > 0 else "skipped"
        elif completed >= expected:
            status_str = "completed"
        elif completed > 0 or skipped > 0:
            status_str = "partial"
        else:
            status_str = "missed"
        
        days.append(DailyCompletionStatus(
            date=d.isoformat(),
            status=status_str,
            expected=expected,
            completed=completed,
            skipped=skipped,
        ))
    
    # Calculate summary stats
    total_expected = sum(d.expected for d in days)
    total_completed = sum(d.completed for d in days)
    total_skipped = sum(d.skipped for d in days)
    total_missed = max(0, total_expected - total_completed - total_skipped)
    completion_rate = total_completed / total_expected if total_expected > 0 else 0.0
    
    current_streak, longest_streak = calculate_streak(
        completions, end.date(), expected_dates
    )
    
    completed_completions = [c for c in completions if c.status == "completed"]
    last_completed_at = (
        completed_completions[-1].completed_at if completed_completions else None
    )
    
    return CompletionHistoryResponse(
        task_id=task_id,
        period=TaskStatsPeriod(start=start, end=end),
        days=days,
        summary=TaskStatsResponse(
            task_id=task_id,
            period=TaskStatsPeriod(start=start, end=end),
            total_expected=total_expected,
            total_completed=total_completed,
            total_skipped=total_skipped,
            total_missed=total_missed,
            completion_rate=round(completion_rate, 3),
            current_streak=current_streak,
            longest_streak=longest_streak,
            last_completed_at=last_completed_at,
        ),
    )
