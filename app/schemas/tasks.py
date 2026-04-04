"""
Pydantic schemas for Tasks API.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Type Aliases
# ============================================================================

SchedulingMode = Literal["floating", "fixed"]
TaskStatus = Literal["pending", "completed", "skipped"]
CompletionStatus = Literal["completed", "skipped"]


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
    scheduled_at: datetime | None = None
    
    # Phase 4b: Scheduling mode for recurring tasks
    # 'floating' = "Time-of-day" (7am wherever you are)
    # 'fixed' = "Fixed time" (timezone-locked)
    scheduling_mode: str | None = None
    
    is_recurring: bool = False
    recurrence_rule: str | None = None
    notify_before_minutes: int | None = None
    completed_at: datetime | None = None
    
    # Phase 4b: Skip reason (optional)
    skip_reason: str | None = None
    
    created_at: datetime
    updated_at: datetime

    # Computed properties
    is_lightning: bool = False

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
    scheduled_at: datetime | None = Field(
        default=None, description="When user plans to do this task"
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
        description="'floating' (time-of-day) or 'fixed' (timezone-locked). Required for recurring tasks with times."
    )
    
    notify_before_minutes: int | None = Field(
        default=None, ge=0, description="Notify N minutes before scheduled time"
    )


class UpdateTaskRequest(BaseModel):
    """Request to update an existing task."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    duration_minutes: int | None = Field(default=None, ge=0)
    scheduled_at: datetime | None = None
    notify_before_minutes: int | None = None
    goal_id: str | None = Field(default=None, description="Move task to different goal")
    
    # Phase 4b: Recurrence fields
    is_recurring: bool | None = None
    recurrence_rule: str | None = None
    scheduling_mode: SchedulingMode | None = None


class CompleteTaskRequest(BaseModel):
    """Request to mark a task as complete."""

    # For recurring tasks (Phase 4b), can specify which occurrence was completed
    scheduled_for: datetime | None = Field(
        default=None,
        description="For recurring tasks: which occurrence was completed"
    )


class SkipTaskRequest(BaseModel):
    """Request to skip a task."""

    reason: str | None = Field(default=None, max_length=500, description="Optional reason for skipping")
    scheduled_for: datetime | None = Field(
        default=None,
        description="For recurring tasks: which occurrence was skipped"
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
