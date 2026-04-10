"""
Task Completions API endpoints.

Provides completion management for Time Machine and Rhythm History Simulator.
"""
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.models import Task
from app.models.task_completion import TaskCompletion
from app.schemas.tasks import (
    BulkCompletionsRequest,
    BulkCompletionsResponse,
    DeleteMockCompletionsResponse,
)
from app.api.helpers.task_helpers import get_task_or_404

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ============================================================================
# Time Machine Endpoints
# ============================================================================


@router.get(
    "/completions/future/count",
    summary="Count future completions",
)
async def count_future_completions(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    after_date: str | None = Query(
        None,
        description="Count completions after this date (YYYY-MM-DD). Defaults to today if not provided.",
    ),
) -> dict[str, int]:
    """
    Count task completions dated after the specified date.
    
    Used by the Time Machine feature to show the user how many completions
    would be affected when reverting to an earlier date.
    """
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
    
    count_stmt = select(func.count()).select_from(TaskCompletion).where(
        and_(
            TaskCompletion.task_id.in_(
                select(Task.id).where(Task.user_id == user.id)
            ),
            func.date(TaskCompletion.scheduled_for) > cutoff_date
        )
    )
    result = await db.execute(count_stmt)
    count = result.scalar() or 0
    
    return {"count": count}


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


# ============================================================================
# Rhythm History Simulator Endpoints (Phase 4h)
# ============================================================================


@router.post(
    "/{task_id}/completions/bulk",
    response_model=BulkCompletionsResponse,
    summary="Create bulk completions (Rhythm Simulator)",
)
async def create_bulk_completions(
    task_id: str,
    request: BulkCompletionsRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkCompletionsResponse:
    """
    Create bulk completions for a recurring task.

    Used by the Rhythm History Simulator to rapidly model completion history
    without waiting weeks to accumulate real data.

    All created completions are marked with source='MOCK' for filtering.
    Optionally updates the task's start date (scheduled_date) for modeling.

    Returns the count of created completions.
    """
    task = await get_task_or_404(db, task_id, user.id)

    if not task.is_recurring:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bulk completions only supported for recurring tasks",
        )

    # Clear existing mock completions first (replace, not add)
    delete_stmt = delete(TaskCompletion).where(
        TaskCompletion.task_id == task.id,
        TaskCompletion.source == "MOCK",
    )
    await db.execute(delete_stmt)

    # Optionally update task start date
    start_date_updated = False
    if request.update_start_date:
        task.scheduled_date = request.update_start_date
        # Also clear scheduled_at if present to avoid confusion
        if task.scheduled_at and request.update_start_date:
            # Preserve time portion but update date
            original_time = task.scheduled_at
            new_date = datetime.strptime(request.update_start_date, "%Y-%m-%d")
            task.scheduled_at = datetime(
                new_date.year,
                new_date.month,
                new_date.day,
                original_time.hour,
                original_time.minute,
                original_time.second,
                tzinfo=timezone.utc,
            )
        start_date_updated = True

    created_count = 0
    for entry in request.entries:
        # Parse the date
        try:
            entry_date = datetime.strptime(entry.date, "%Y-%m-%d")
        except ValueError:
            continue  # Skip invalid dates

        # Create completion record(s) for this date
        for occ in range(entry.occurrences):
            # Create a scheduled_for time for this occurrence
            # Spread occurrences throughout the day
            hour = max(0, min(23, 8 + (occ * 4)))  # 8am, 12pm, 4pm, etc.
            scheduled_for = datetime(
                entry_date.year,
                entry_date.month,
                entry_date.day,
                hour,
                0,
                0,
                tzinfo=timezone.utc,
            )

            completion = TaskCompletion(
                task_id=task.id,
                status=entry.status,
                skip_reason=entry.skip_reason if entry.status == "skipped" else None,
                completed_at=scheduled_for,  # Record as completed at scheduled time
                scheduled_for=scheduled_for,
                local_date=entry.date,
                source="MOCK",
            )
            db.add(completion)
            created_count += 1

    await db.commit()

    return BulkCompletionsResponse(
        created_count=created_count,
        task_id=task.id,
        start_date_updated=start_date_updated,
    )


@router.delete(
    "/{task_id}/completions/mock",
    response_model=DeleteMockCompletionsResponse,
    summary="Delete mock completions (Rhythm Simulator)",
)
async def delete_mock_completions(
    task_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeleteMockCompletionsResponse:
    """
    Delete all mock completions for a recurring task.

    Removes all completions marked with source='MOCK' for this task,
    leaving real (source='REAL') completions intact.

    Used by the Rhythm History Simulator to clear test data.
    """
    task = await get_task_or_404(db, task_id, user.id)

    # Count how many will be deleted
    count_stmt = select(func.count()).select_from(TaskCompletion).where(
        and_(
            TaskCompletion.task_id == task.id,
            TaskCompletion.source == "MOCK",
        )
    )
    result = await db.execute(count_stmt)
    deleted_count = result.scalar() or 0

    # Delete mock completions
    if deleted_count > 0:
        delete_stmt = delete(TaskCompletion).where(
            and_(
                TaskCompletion.task_id == task.id,
                TaskCompletion.source == "MOCK",
            )
        )
        await db.execute(delete_stmt)
        await db.commit()

    return DeleteMockCompletionsResponse(
        deleted_count=deleted_count,
        task_id=task.id,
    )
