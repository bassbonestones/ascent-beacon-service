"""
Pydantic schemas for Tasks API.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Type Aliases
# ============================================================================

# 'floating' = time-of-day (adjusts with timezone)
# 'fixed' = fixed time (timezone-locked)
# 'date_only' = only date is set, no specific time
# 'anytime' = no schedule, shown in backlog tab with manual ordering (Phase 4e)
SchedulingMode = Literal["floating", "fixed", "date_only", "anytime"]
TaskStatus = Literal["pending", "completed", "skipped"]
CompletionStatus = Literal["completed", "skipped"]

# Phase 4g: Recurrence behavior for recurring tasks
# 'habitual' = auto-skip missed occurrences on app open
# 'essential' = stays overdue until manually actioned
RecurrenceBehavior = Literal["habitual", "essential"]


# ============================================================================
# Shared/Nested Schemas
# ============================================================================


class GoalInfo(BaseModel):
    """Brief info about a linked goal."""

    id: str
    title: str
    status: str

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Task Completion Schemas (Phase 4b)
# ============================================================================


class TaskCompletionResponse(BaseModel):
    """Response for a single task completion record."""

    id: str
    task_id: str
    status: str  # completed | skipped
    skip_reason: str | None = None
    completed_at: datetime
    scheduled_for: datetime | None = None
    source: str | None = None  # REAL | MOCK
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskCompletionListResponse(BaseModel):
    """Response for listing task completions."""

    completions: list[TaskCompletionResponse]
    total: int = 0
    completed_count: int = 0
    skipped_count: int = 0


# ============================================================================
# Task Response Schemas
# ============================================================================


class TaskResponse(BaseModel):
    """Full task response."""

    id: str
    user_id: str
    goal_id: str | None = None
    title: str
    description: str | None = None
    duration_minutes: int = 0
    status: str  # pending | completed | skipped
    
    # Scheduling: scheduled_date for date-only, scheduled_at for date+time
    scheduled_date: str | None = None  # YYYY-MM-DD format, for date-only tasks
    scheduled_at: datetime | None = None  # For timed tasks (includes date+time)
    
    # Phase 4b: Scheduling mode for recurring tasks
    # 'floating' = "Time-of-day" (7am wherever you are)
    # 'fixed' = "Fixed time" (timezone-locked)
    # 'date_only' = only date is set, no specific time
    # 'anytime' = no schedule, backlog task (Phase 4e)
    scheduling_mode: str | None = None
    
    is_recurring: bool = False
    recurrence_rule: str | None = None
    notify_before_minutes: int | None = None
    completed_at: datetime | None = None
    
    # Phase 4b: Skip reason (optional)
    skip_reason: str | None = None
    
    # Phase 4g: Recurrence behavior for recurring tasks
    # 'habitual' = auto-skip missed, 'essential' = stays overdue
    recurrence_behavior: str | None = None
    
    # Phase 4e: Sort order for anytime tasks (lower = higher in list)
    sort_order: int | None = None
    
    created_at: datetime
    updated_at: datetime

    # Computed properties
    is_lightning: bool = False
    
    # Phase 4b: For recurring tasks, indicates if completed for today
    completed_for_today: bool = False
    
    # Phase 4b: For recurring tasks with multiple daily occurrences, 
    # how many completions recorded for today
    completions_today: int = 0
    
    # Phase 4b: For interval/specific_times modes, the actual times completed today
    # ISO datetime strings for each completion
    completed_times_today: list[str] = []
    
    # Phase 4b: For recurring tasks, completions indexed by date (YYYY-MM-DD)
    # Maps date string to list of ISO datetime strings for completions on that date
    # Used for Upcoming view to show future occurrences as completed
    completions_by_date: dict[str, list[str]] = {}
    
    # Phase 4b: For recurring tasks, indicates if skipped for today
    skipped_for_today: bool = False
    
    # Phase 4b: For recurring tasks, how many skips recorded for today
    skips_today: int = 0
    
    # Phase 4b: For recurring tasks, the actual times skipped today
    skipped_times_today: list[str] = []
    
    # Phase 4b: For recurring tasks, the skip reason for today (most recent)
    skip_reason_today: str | None = None
    
    # Phase 4b: For recurring tasks, skips indexed by date (YYYY-MM-DD)
    skips_by_date: dict[str, list[str]] = {}
    
    # Phase 4b: For recurring tasks, skip reasons indexed by date (YYYY-MM-DD)
    skip_reasons_by_date: dict[str, str | None] = {}

    # Linked goal info (populated via eager loading)
    goal: GoalInfo | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_task(cls, task: "TaskResponse") -> "TaskResponse":
        """Create response from task model with computed properties."""
        data = task.__dict__.copy() if hasattr(task, "__dict__") else {}
        data["is_lightning"] = task.duration_minutes == 0 if hasattr(task, "duration_minutes") else False
        return cls.model_validate(data)


class TaskListResponse(BaseModel):
    """Response for listing tasks."""

    tasks: list[TaskResponse]
    total: int = 0
    pending_count: int = 0
    completed_count: int = 0


# ============================================================================
# Request Schemas
# ============================================================================


class CreateTaskRequest(BaseModel):
    """Request to create a new task."""

    goal_id: str | None = Field(default=None, description="ID of the goal this task belongs to (optional)")
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    duration_minutes: int = Field(
        default=0,
        ge=0,
        description="Duration in minutes. 0 = lightning task (<1 min)",
    )
    # Scheduling: Use scheduled_date for date-only, scheduled_at for date+time
    scheduled_date: str | None = Field(
        default=None, description="Date only (YYYY-MM-DD) - use when no specific time"
    )
    scheduled_at: datetime | None = Field(
        default=None, description="Full datetime - use when task has a specific time"
    )
    
    # Phase 4b: Recurrence fields
    is_recurring: bool = Field(
        default=False, description="Whether this task recurs"
    )
    recurrence_rule: str | None = Field(
        default=None, 
        max_length=500,
        description="iCal RRULE string (e.g., 'FREQ=DAILY;BYHOUR=9')"
    )
    scheduling_mode: SchedulingMode | None = Field(
        default=None,
        description="'floating' (time-of-day), 'fixed' (timezone-locked), or 'anytime' (backlog). Required for recurring tasks with times."
    )
    recurrence_behavior: RecurrenceBehavior | None = Field(
        default=None,
        description="'habitual' (auto-skip missed) or 'essential' (stays overdue). Required for recurring tasks."
    )
    
    notify_before_minutes: int | None = Field(
        default=None, ge=0, description="Notify N minutes before scheduled time"
    )


class UpdateTaskRequest(BaseModel):
    """Request to update an existing task."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    duration_minutes: int | None = Field(default=None, ge=0)
    # Scheduling: Use scheduled_date for date-only, scheduled_at for date+time
    # Send scheduled_date with scheduled_at=null to make date-only
    # Send scheduled_at with scheduled_date=null to make timed
    scheduled_date: str | None = None
    scheduled_at: datetime | None = None
    notify_before_minutes: int | None = None
    goal_id: str | None = Field(default=None, description="Move task to different goal")
    
    # Phase 4b: Recurrence fields
    is_recurring: bool | None = None
    recurrence_rule: str | None = None
    scheduling_mode: SchedulingMode | None = None
    recurrence_behavior: RecurrenceBehavior | None = None


class CompleteTaskRequest(BaseModel):
    """Request to mark a task as complete."""

    # For recurring tasks (Phase 4b), can specify which occurrence was completed
    scheduled_for: datetime | None = Field(
        default=None,
        description="For recurring tasks: which occurrence was completed"
    )
    local_date: str | None = Field(
        default=None,
        description="Client's local date (YYYY-MM-DD) for this occurrence"
    )


class SkipTaskRequest(BaseModel):
    """Request to skip a task."""

    reason: str | None = Field(default=None, max_length=500, description="Optional reason for skipping")
    scheduled_for: datetime | None = Field(
        default=None,
        description="For recurring tasks: which occurrence was skipped"
    )
    local_date: str | None = Field(
        default=None,
        description="Client's local date (YYYY-MM-DD) for this occurrence"
    )


class ReopenTaskRequest(BaseModel):
    """Request to reopen a task."""

    scheduled_for: datetime | None = Field(
        default=None,
        description="For recurring tasks: which occurrence to undo (delete completion)"
    )
    local_date: str | None = Field(
        default=None,
        description="Client's local date (YYYY-MM-DD) for this occurrence"
    )


class ReorderTaskRequest(BaseModel):
    """Request to reorder an anytime task (Phase 4e)."""

    new_position: int = Field(
        ...,
        ge=1,
        description="New position in the list (1 = top). Tasks below this position shift down."
    )


# ============================================================================
# Today/Range View Schemas (Phase 4b)
# ============================================================================


class TodayTasksResponse(BaseModel):
    """Response for today's tasks view."""

    tasks: list[TaskResponse]
    pending_count: int = 0
    completed_today_count: int = 0
    overdue_count: int = 0


# ============================================================================
# Anytime Tasks Schemas (Phase 4e)
# ============================================================================


class AnytimeTasksResponse(BaseModel):
    """Response for anytime tasks view (backlog)."""

    tasks: list[TaskResponse]
    total: int = 0


class ReorderTaskResponse(BaseModel):
    """Response after reordering a task."""

    task: TaskResponse


class TaskRangeRequest(BaseModel):
    """Request for tasks in a date range (All view with pagination)."""

    start_date: datetime
    end_date: datetime
    include_completed: bool = Field(default=False)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class TaskRangeResponse(BaseModel):
    """Response for tasks in a date range."""

    tasks: list[TaskResponse]
    total: int
    has_more: bool = False
    start_date: datetime
    end_date: datetime


# ============================================================================
# Stats Schemas (Phase 4c)
# ============================================================================


class TaskStatsPeriod(BaseModel):
    """Time period for stats calculation."""

    start: datetime
    end: datetime


class TaskStatsResponse(BaseModel):
    """Response for task stats (habit tracking)."""

    task_id: str
    period: TaskStatsPeriod
    total_expected: int  # Based on RRULE for recurring tasks
    total_completed: int
    total_skipped: int
    total_missed: int  # Expected - completed - skipped
    completion_rate: float  # completed / expected
    current_streak: int  # Consecutive completions ending today
    longest_streak: int  # Best streak ever in period
    last_completed_at: datetime | None = None


class DailyCompletionStatus(BaseModel):
    """Status for a single day in completion history."""

    date: str  # YYYY-MM-DD
    status: str  # completed | skipped | missed | partial (for multi-occurrence)
    expected: int = 1  # Expected completions for this day
    completed: int = 0  # Actual completions
    skipped: int = 0


class CompletionHistoryResponse(BaseModel):
    """Response for completion history (calendar data)."""

    task_id: str
    period: TaskStatsPeriod
    days: list[DailyCompletionStatus]
    summary: TaskStatsResponse


# ============================================================================
# Time Machine Schemas
# ============================================================================


class DeleteFutureCompletionsResponse(BaseModel):
    """Response for deleting future completions (time machine reset)."""

    deleted_count: int


# ============================================================================
# Rhythm History Simulator Schemas (Phase 4h)
# ============================================================================


class BulkCompletionEntry(BaseModel):
    """Single entry for bulk completion creation."""

    date: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Date in YYYY-MM-DD format"
    )
    status: Literal["completed", "skipped"] = Field(
        default="completed",
        description="Status for all occurrences on this date"
    )
    skip_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason when status is 'skipped'"
    )
    occurrences: int = Field(
        default=1,
        ge=1,
        le=20,
        description="Number of occurrences to create for this date"
    )


class BulkCompletionsRequest(BaseModel):
    """Request to create bulk completions for Rhythm History Simulator."""

    entries: list[BulkCompletionEntry] = Field(
        ...,
        min_length=1,
        max_length=365,
        description="List of dates with completion status"
    )
    update_start_date: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Optional: update task's scheduled_date to this value"
    )


class BulkCompletionsResponse(BaseModel):
    """Response for bulk completion creation."""

    created_count: int
    task_id: str
    start_date_updated: bool = False


class DeleteMockCompletionsResponse(BaseModel):
    """Response for deleting mock completions."""

    deleted_count: int
    task_id: str
