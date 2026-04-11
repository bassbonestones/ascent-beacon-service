"""
Tasks List API endpoint.

Provides the list_tasks endpoint with completion tracking.
Split from tasks_crud.py due to complexity of completion tracking logic.
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.models import Task
from app.models.task_completion import TaskCompletion
from app.schemas.tasks import TaskDependencySummary, TaskListResponse
from app.api.helpers.task_helpers import task_to_response
from app.services.task_dependency_summary import build_summaries_for_tasks

router = APIRouter(prefix="/tasks", tags=["tasks"])


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
    include_dependency_summary: bool = Query(
        default=False,
        description="When true with client_today, include dependency_summary on each task that has downstream rules",
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
                TaskCompletion.completed_at,
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
        all_completion_rows = completion_result.fetchall()
        for row in all_completion_rows:
            task_id = row[0]
            scheduled_for = row[1]
            record_status = row[2]  # "completed" or "skipped"
            skip_reason = row[3]  # skip reason (null for completions)
            local_date = row[4]  # client's local date (YYYY-MM-DD)
            completed_at = row[5]

            if not local_date and not scheduled_for and not completed_at:
                continue

            if local_date:
                date_key = local_date
            elif scheduled_for:
                sf = scheduled_for
                if sf.tzinfo is None:
                    sf = sf.replace(tzinfo=timezone.utc)
                date_key = sf.strftime("%Y-%m-%d")
            else:
                ca = completed_at
                if ca is None:
                    continue
                if ca.tzinfo is None:
                    ca = ca.replace(tzinfo=timezone.utc)
                date_key = ca.strftime("%Y-%m-%d")

            if scheduled_for:
                sf = scheduled_for
                if sf.tzinfo is None:
                    sf = sf.replace(tzinfo=timezone.utc)
                ts_iso = sf.isoformat()
            elif completed_at:
                ca = completed_at
                if ca.tzinfo is None:
                    ca = ca.replace(tzinfo=timezone.utc)
                ts_iso = ca.isoformat()
            else:
                ts_iso = f"{date_key}T12:00:00+00:00"

            if record_status == "completed":
                if task_id not in completions_by_date_map:
                    completions_by_date_map[task_id] = {}
                if date_key not in completions_by_date_map[task_id]:
                    completions_by_date_map[task_id][date_key] = []
                completions_by_date_map[task_id][date_key].append(ts_iso)

                if date_key == today_str:
                    completions_today_count[task_id] = completions_today_count.get(task_id, 0) + 1
                    if task_id not in completions_today_times:
                        completions_today_times[task_id] = []
                    completions_today_times[task_id].append(ts_iso)
            else:
                if task_id not in skips_by_date_map:
                    skips_by_date_map[task_id] = {}
                if date_key not in skips_by_date_map[task_id]:
                    skips_by_date_map[task_id][date_key] = []
                skips_by_date_map[task_id][date_key].append(ts_iso)

                if task_id not in skip_reasons_by_date_map:
                    skip_reasons_by_date_map[task_id] = {}
                skip_reasons_by_date_map[task_id][date_key] = skip_reason

                if date_key == today_str:
                    skips_today_count[task_id] = skips_today_count.get(task_id, 0) + 1
                    if task_id not in skips_today_times:
                        skips_today_times[task_id] = []
                    skips_today_times[task_id].append(ts_iso)
                    skip_reason_today_map[task_id] = skip_reason

    # Count stats
    pending_count = sum(1 for t in tasks if t.status == "pending")
    completed_count = sum(1 for t in tasks if t.status == "completed")

    summaries: dict[str, TaskDependencySummary] = {}
    if include_dependency_summary and client_today:
        summaries = await build_summaries_for_tasks(db, user.id, tasks, client_today)

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
                dependency_summary=summaries.get(t.id),
            )
            for t in tasks
        ],
        total=len(tasks),
        pending_count=pending_count,
        completed_count=completed_count,
    )
