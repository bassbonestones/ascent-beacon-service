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


class Task(Base, UUIDMixin, TimestampMixin):
    """
    Actionable item belonging to a goal.
    
    Tasks represent concrete work to be done. They can be:
    - One-time tasks with optional scheduling
    - Lightning tasks (duration=0, <1 minute)
    - Recurring tasks with RRULE (Phase 4b)
    
    Scheduling modes for recurring tasks with times:
    - 'floating' = "Time-of-day" (7am wherever you are, adjusts with timezone)
    - 'fixed' = "Fixed time" (timezone-locked, e.g., 2pm EST always)
    
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

    # Scheduling (when user plans to do it)
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

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tasks")
    goal: Mapped["Goal"] = relationship("Goal", back_populates="tasks")
    completions: Mapped[List["TaskCompletion"]] = relationship(
        "TaskCompletion",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskCompletion.completed_at.desc()",
    )

    __table_args__ = (
        Index("ix_tasks_user_id", "user_id"),
        Index("ix_tasks_goal_id", "goal_id"),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_scheduled_at", "scheduled_at"),
        Index("ix_tasks_is_recurring", "is_recurring"),
        Index("ix_tasks_user_status", "user_id", "status"),
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

    def __repr__(self) -> str:
        status_icon = "✓" if self.is_completed else "○"
        lightning = "⚡" if self.is_lightning else ""
        return f"<Task {status_icon}{lightning} '{self.title[:25]}...'>"
