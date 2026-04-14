"""
Pydantic schemas for Goals API.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ============================================================================
# Shared/Nested Schemas
# ============================================================================


class GoalPriorityLinkResponse(BaseModel):
    """A goal-priority link."""

    id: str
    priority_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriorityInfo(BaseModel):
    """Brief info about a linked priority."""

    id: str
    title: str
    score: int | None = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Goal Response Schemas
# ============================================================================


class GoalResponse(BaseModel):
    """Full goal response."""

    id: str
    user_id: str
    parent_goal_id: str | None = None
    title: str
    description: str | None = None
    target_date: date | None = None
    status: str  # not_started | in_progress | completed (derived)
    progress_cached: int = 0
    total_time_minutes: int = 0
    completed_time_minutes: int = 0
    has_incomplete_breakdown: bool = True
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    # Phase 4j
    record_state: str = "active"
    archived_at: datetime | None = None
    archive_tracking_mode: str | None = None
    is_aligned_with_priorities: bool = True

    # Linked priorities (populated via eager loading)
    priorities: list[PriorityInfo] = []

    model_config = ConfigDict(from_attributes=True)


class GoalWithSubGoalsResponse(GoalResponse):
    """Goal response including sub-goals (tree view)."""

    sub_goals: list["GoalWithSubGoalsResponse"] = []
    # Tasks will be added when Tasks Engine is implemented
    # tasks: list[TaskResponse] = []


class GoalListResponse(BaseModel):
    """Response for listing goals."""

    goals: list[GoalResponse]
    reschedule_count: int = 0  # Number of goals past target date


# ============================================================================
# Request Schemas
# ============================================================================


class CreateGoalRequest(BaseModel):
    """Request to create a new goal."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    target_date: date | None = None
    priority_ids: list[str] = Field(default_factory=list)  # Optional, array
    parent_goal_id: str | None = None  # Optional, for sub-goals


class UpdateGoalRequest(BaseModel):
    """Request to update an existing goal."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    target_date: date | None = None
    parent_goal_id: str | None = None  # Reparent goal
    priority_id: str | None = Field(
        default=None,
        description="When set (including null), replaces all priority links for this goal.",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_status_in_payload(cls, data: object) -> object:
        if isinstance(data, dict) and "status" in data:
            raise ValueError("Goal status is derived and cannot be set via the API")
        return data


class SetPriorityLinksRequest(BaseModel):
    """Request to set priority links (replaces all existing)."""

    priority_ids: list[str]


class RescheduleGoalsRequest(BaseModel):
    """Request to reschedule multiple goals."""

    goal_updates: list["GoalRescheduleItem"]


class GoalRescheduleItem(BaseModel):
    """Single goal reschedule update."""

    goal_id: str
    new_target_date: date


# ============================================================================
# Phase 4j — Archive
# ============================================================================


class ArchivePreviewTaskItem(BaseModel):
    """One task that needs a resolution before archiving."""

    task_id: str
    goal_id: str | None = None
    title: str


class ArchivePreviewResponse(BaseModel):
    """Preview of goal archive impact."""

    goal_id: str
    subtree_goal_ids: list[str]
    tasks_requiring_resolution: list[ArchivePreviewTaskItem]


class TaskResolutionItem(BaseModel):
    """Per-task choice when archiving a goal subtree."""

    task_id: str
    action: Literal["reassign", "keep_unaligned", "pause_task", "archive_task"]
    goal_id: str | None = None


class ArchiveGoalRequest(BaseModel):
    """Commit goal archive with mandatory task resolutions."""

    tracking_mode: Literal["failed", "ignored"]
    task_resolutions: list[TaskResolutionItem] = Field(default_factory=list)


# ============================================================================
# Forward references
# ============================================================================

GoalWithSubGoalsResponse.model_rebuild()
