from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.goal import Goal
    from app.models.task_completion import TaskCompletion
    from app.models.user import User
    from app.models.occurrence_preference import OccurrencePreference
    from app.models.daily_sort_override import DailySortOverride
    from app.models.dependency import DependencyRule, DependencyStateCache


class Task(Base, UUIDMixin, TimestampMixin):
    """
    Actionable item belonging to a goal.
    
    Tasks represent concrete work to be done. They can be:
    - One-time tasks with optional scheduling
    - Lightning tasks (duration=0, <1 minute)
    - Recurring tasks with RRULE (Phase 4b)
    - Anytime tasks (no schedule, user-ordered backlog) (Phase 4e)
    
    Scheduling modes:
    - 'floating' = "Time-of-day" (7am wherever you are, adjusts with timezone)
    - 'fixed' = "Fixed time" (timezone-locked, e.g., 2pm EST always)
    - 'date_only' = Date without specific time
    - 'anytime' = No schedule, shown in backlog tab with manual ordering
    
    Task completion drives goal progress calculation.
    """

    __tablename__ = "tasks"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    goal_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("goals.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Core fields
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # Duration: 0 = lightning task (<1 min, shown as ⚡ checkbox)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Status: pending | completed | skipped
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")

    # Scheduling: scheduled_date for the date, scheduled_at for the time
    # - For date-only tasks: scheduled_date is set, scheduled_at is NULL
    # - For timed tasks: scheduled_at is set (includes date+time), scheduled_date may be NULL
    # - For unscheduled tasks: both are NULL (defaults to "today" in the UI)
    scheduled_date: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # YYYY-MM-DD format
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Phase 4b: Scheduling mode for recurring tasks with times
    # 'floating' = "Time-of-day" (7am wherever you are, adjusts with timezone)
    # 'fixed' = "Fixed time" (timezone-locked, e.g., 2pm EST always)
    # NULL for tasks without specific times
    scheduling_mode: Mapped[str | None] = mapped_column(String, nullable=True)

    # Recurrence (Phase 4b) - RRULE string
    recurrence_rule: Mapped[str | None] = mapped_column(String, nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Notifications (Phase 4f) - NULL = no notification
    notify_before_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Completion tracking (for non-recurring tasks)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Phase 4b: Optional reason when task is skipped
    skip_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    # Phase 4g: Recurrence behavior for recurring tasks
    # 'habitual' = Auto-skip missed occurrences on app open
    # 'essential' = Stays overdue until manually actioned
    # NULL for non-recurring tasks, required for recurring tasks
    recurrence_behavior: Mapped[str | None] = mapped_column(String, nullable=True)

    # Phase 4j: visibility / lifecycle (separate from workflow status)
    record_state: Mapped[str] = mapped_column(String, nullable=False, default="active")
    unaligned_execution_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Phase 4e: Sort order for anytime tasks (manual ordering)
    # NULL for non-anytime tasks, integer for anytime (lower = higher in list)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tasks")
    goal: Mapped["Goal"] = relationship("Goal", back_populates="tasks")
    completions: Mapped[List["TaskCompletion"]] = relationship(
        "TaskCompletion",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskCompletion.completed_at.desc()",
    )
    occurrence_preferences: Mapped[List["OccurrencePreference"]] = relationship(
        "OccurrencePreference",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    daily_sort_overrides: Mapped[List["DailySortOverride"]] = relationship(
        "DailySortOverride",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    # Phase 4i: Dependency relationships
    # Rules where this task is the upstream (prerequisite)
    downstream_dependency_rules: Mapped[List["DependencyRule"]] = relationship(
        "DependencyRule",
        foreign_keys="DependencyRule.upstream_task_id",
        back_populates="upstream_task",
        cascade="all, delete-orphan",
    )
    # Rules where this task is the downstream (dependent)
    upstream_dependency_rules: Mapped[List["DependencyRule"]] = relationship(
        "DependencyRule",
        foreign_keys="DependencyRule.downstream_task_id",
        back_populates="downstream_task",
        cascade="all, delete-orphan",
    )
    # Cached dependency state for this task's occurrences
    dependency_state_cache: Mapped[List["DependencyStateCache"]] = relationship(
        "DependencyStateCache",
        back_populates="task",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_tasks_user_id", "user_id"),
        Index("ix_tasks_goal_id", "goal_id"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_scheduled_at", "scheduled_at"),
        Index("ix_tasks_is_recurring", "is_recurring"),
        Index("ix_tasks_user_status", "user_id", "status"),
        Index("ix_tasks_record_state", "record_state"),
    )

    @property
    def is_lightning(self) -> bool:
        """Lightning tasks take <1 minute (duration=0)."""
        return self.duration_minutes == 0

    @property
    def is_completed(self) -> bool:
        """Check if task is completed."""
        return self.status == "completed"

    @property
    def is_pending(self) -> bool:
        """Check if task is pending."""
        return self.status == "pending"

    @property
    def is_floating(self) -> bool:
        """Check if task uses floating/time-of-day scheduling."""
        return self.scheduling_mode == "floating"

    @property
    def is_fixed_time(self) -> bool:
        """Check if task uses fixed/timezone-locked scheduling."""
        return self.scheduling_mode == "fixed"

    @property
    def is_anytime(self) -> bool:
        """Check if task is an anytime task (no schedule, backlog)."""
        return self.scheduling_mode == "anytime"

    @property
    def is_habitual(self) -> bool:
        """Check if task has habitual behavior (auto-skip missed)."""
        return self.recurrence_behavior == "habitual"

    @property
    def is_essential(self) -> bool:
        """Check if task has essential behavior (stays overdue)."""
        return self.recurrence_behavior == "essential"

    def __repr__(self) -> str:
        status_icon = "✓" if self.is_completed else "○"
        lightning = "⚡" if self.is_lightning else ""
        return f"<Task {status_icon}{lightning} '{self.title[:25]}...'>"
