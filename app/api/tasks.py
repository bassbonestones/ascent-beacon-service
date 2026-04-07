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
    ReopenTaskRequest,
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
    client_today: str | None = Query(
        default=None, description="Client's local date as YYYY-MM-DD for 'today' calculations"
    ),
    days_ahead: int = Query(
        default=14, ge=1, le=365, description="How many days ahead to load completion data for recurring tasks"
    ),
) -> TaskListResponse:
    """Get all tasks for the current user, with optional filters."""
    # Determine "today" - prefer client's local date if provided
    # This fixes timezone issues where UTC "today" differs from user's local "today"
    if client_today:
        # Parse client's date string (YYYY-MM-DD)
        try:
            today_date = datetime.strptime(client_today, "%Y-%m-%d").date()
        except ValueError:
            # Invalid format, fall back to UTC
            now = datetime.now(timezone.utc)
            today_date = now.date()
    else:
        now = datetime.now(timezone.utc)
        today_date = now.date()
    
    # Convert to "today" string for date comparisons
    today_str = today_date.strftime("%Y-%m-%d")
    
    # For datetime range queries (used in include_completed filter), use UTC bounds
    # but extend back to capture any completion on the client's "today"
    now = datetime.now(timezone.utc)
    start_of_day = datetime.combine(today_date, datetime.min.time(), tzinfo=timezone.utc)
    end_of_day = start_of_day + timedelta(days=1) - timedelta(microseconds=1)
    # Extended range for Upcoming view (controlled by days_ahead param)
    end_of_range = start_of_day + timedelta(days=days_ahead + 1)
    
    # Get IDs of recurring tasks completed or skipped today
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
    
    # Get IDs of recurring tasks completed in the upcoming range (for Upcoming view)
    completed_in_range_subquery = (
        select(TaskCompletion.task_id)
        .join(Task, Task.id == TaskCompletion.task_id)
        .where(
            and_(
                Task.user_id == user.id,
                Task.is_recurring == True,  # noqa: E712
                TaskCompletion.status.in_(["completed", "skipped"]),
                TaskCompletion.scheduled_for >= start_of_day,
                TaskCompletion.scheduled_for < end_of_range,
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
        # Include: non-recurring completed tasks OR recurring tasks completed in range
        # This allows Upcoming view to show recurring tasks completed for future dates
        stmt = stmt.where(
            or_(
                and_(Task.is_recurring == False, Task.status == "completed"),  # noqa: E712
                Task.id.in_(completed_in_range_subquery),
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
    
    # Get completion info for recurring tasks
    # Query completions for today AND the next 14 days (for Upcoming view)
    recurring_task_ids = [t.id for t in tasks if t.is_recurring]
    completions_today_count: dict[str, int] = {}
    completions_today_times: dict[str, list[str]] = {}
    completions_by_date_map: dict[str, dict[str, list[str]]] = {}  # task_id -> date -> times
    # Separate tracking for skips
    skips_today_count: dict[str, int] = {}
    skips_today_times: dict[str, list[str]] = {}
    skips_by_date_map: dict[str, dict[str, list[str]]] = {}  # task_id -> date -> times
    # Skip reason tracking
    skip_reason_today_map: dict[str, str | None] = {}  # task_id -> reason
    skip_reasons_by_date_map: dict[str, dict[str, str | None]] = {}  # task_id -> date -> reason
    
    if recurring_task_ids:
        # Query for completions in the specified days_ahead range (including today)
        # (end_of_range is defined at the top of the function)
        # Include status, skip_reason, and local_date so we can separate completions from skips
        
        # Calculate date strings for local_date matching
        # (local_date is a YYYY-MM-DD string, not a datetime)
        end_date_str = (today_date + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        
        # Query using OR: match either local_date in range OR scheduled_for in range
        # This handles timezone edge cases where scheduled_for (UTC) might be a day
        # behind local_date for users ahead of UTC
        completion_stmt = (
            select(
                TaskCompletion.task_id,
                TaskCompletion.scheduled_for,
                TaskCompletion.status,
                TaskCompletion.skip_reason,
                TaskCompletion.local_date,
            )
            .where(
                and_(
                    TaskCompletion.task_id.in_(recurring_task_ids),
                    TaskCompletion.status.in_(["completed", "skipped"]),
                    or_(
                        # Match by local_date (new records with timezone-correct date)
                        and_(
                            TaskCompletion.local_date.isnot(None),
                            TaskCompletion.local_date >= today_str,
                            TaskCompletion.local_date <= end_date_str,
                        ),
                        # Match by scheduled_for (backward compat for old records without local_date)
                        and_(
                            TaskCompletion.local_date.is_(None),
                            TaskCompletion.scheduled_for >= start_of_day,
                            TaskCompletion.scheduled_for < end_of_range,
                        ),
                    ),
                )
            )
        )
        completion_result = await db.execute(completion_stmt)
        
        # Build completion data structures
        for row in completion_result.fetchall():
            task_id = row[0]
            scheduled_for = row[1]
            record_status = row[2]  # "completed" or "skipped"
            skip_reason = row[3]  # skip reason (null for completions)
            local_date = row[4]  # client's local date (YYYY-MM-DD)
            
            if scheduled_for:
                # Ensure scheduled_for is timezone-aware for comparison
                if scheduled_for.tzinfo is None:
                    scheduled_for = scheduled_for.replace(tzinfo=timezone.utc)
                
                # Use local_date as the date key if available (for timezone correctness)
                # Fall back to UTC date from scheduled_for for backward compatibility
                if local_date:
                    date_key = local_date
                else:
                    date_key = scheduled_for.strftime("%Y-%m-%d")
                
                if record_status == "completed":
                    # Track completions
                    if task_id not in completions_by_date_map:
                        completions_by_date_map[task_id] = {}
                    if date_key not in completions_by_date_map[task_id]:
                        completions_by_date_map[task_id][date_key] = []
                    completions_by_date_map[task_id][date_key].append(scheduled_for.isoformat())
                    
                    # Track today-specific counts
                    if date_key == today_str:
                        completions_today_count[task_id] = completions_today_count.get(task_id, 0) + 1
                        if task_id not in completions_today_times:
                            completions_today_times[task_id] = []
                        completions_today_times[task_id].append(scheduled_for.isoformat())
                else:
                    # Track skips
                    if task_id not in skips_by_date_map:
                        skips_by_date_map[task_id] = {}
                    if date_key not in skips_by_date_map[task_id]:
                        skips_by_date_map[task_id][date_key] = []
                    skips_by_date_map[task_id][date_key].append(scheduled_for.isoformat())
                    
                    # Track skip reasons by date
                    if task_id not in skip_reasons_by_date_map:
                        skip_reasons_by_date_map[task_id] = {}
                    # Store the most recent skip reason for this date
                    skip_reasons_by_date_map[task_id][date_key] = skip_reason
                    
                    # Track today-specific skip counts
                    if date_key == today_str:
                        skips_today_count[task_id] = skips_today_count.get(task_id, 0) + 1
                        if task_id not in skips_today_times:
                            skips_today_times[task_id] = []
                        skips_today_times[task_id].append(scheduled_for.isoformat())
                        # Store the most recent skip reason for today
                        skip_reason_today_map[task_id] = skip_reason
    
    # Count stats
    pending_count = sum(1 for t in tasks if t.status == "pending")
    completed_count = sum(1 for t in tasks if t.status == "completed")
    
    return TaskListResponse(
        tasks=[
            task_to_response(
                t, 
                completed_for_today=t.id in completions_today_count,
                completions_today=completions_today_count.get(t.id, 0),
                completed_times_today=completions_today_times.get(t.id, []),
                completions_by_date=completions_by_date_map.get(t.id, {}),
                skipped_for_today=t.id in skips_today_count,
                skips_today=skips_today_count.get(t.id, 0),
                skipped_times_today=skips_today_times.get(t.id, []),
                skips_by_date=skips_by_date_map.get(t.id, {}),
                skip_reason_today=skip_reason_today_map.get(t.id),
                skip_reasons_by_date=skip_reasons_by_date_map.get(t.id, {}),
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
            local_date=request.local_date,
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
            local_date=request.local_date,
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
