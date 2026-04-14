from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.goal_priority_link import GoalPriorityLink
    from app.models.task import Task
    from app.models.user import User


class Goal(Base, UUIDMixin, TimestampMixin):
    """
    User goal with optional nesting (sub-goals).
    
    Goals use a mutable model (no revision pattern).
    Progress is cached but calculated from descendant tasks.
    """

    __tablename__ = "goals"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Self-referential for nesting (unlimited depth)
    parent_goal_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Core fields
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Status: not_started | in_progress | completed (derived from task tree)
    status: Mapped[str] = mapped_column(String, nullable=False, default="not_started")

    # Progress cached for performance (recalculated when tasks change)
    progress_cached: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # True if any descendant has no tasks (progress may be inaccurate)
    has_incomplete_breakdown: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Completion timestamp
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Phase 4j: visibility / lifecycle (separate from workflow status)
    # active | paused | archived | deleted
    record_state: Mapped[str] = mapped_column(String, nullable=False, default="active")
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When archiving: failed | ignored (habit stats); NULL if not archived
    archive_tracking_mode: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="goals")
    
    parent: Mapped["Goal | None"] = relationship(
        "Goal",
        remote_side="Goal.id",
        back_populates="sub_goals",
        foreign_keys=[parent_goal_id],
    )
    
    sub_goals: Mapped[list["Goal"]] = relationship(
        "Goal",
        back_populates="parent",
        cascade="all, delete-orphan",
        foreign_keys=[parent_goal_id],
    )
    
    priority_links: Mapped[list["GoalPriorityLink"]] = relationship(
        "GoalPriorityLink",
        back_populates="goal",
        cascade="all, delete-orphan",
    )
    
    tasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="goal",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_goals_user_id", "user_id"),
        Index("ix_goals_parent_goal_id", "parent_goal_id"),
        Index("ix_goals_status", "status"),
        Index("ix_goals_user_status", "user_id", "status"),
        Index("ix_goals_record_state", "record_state"),
    )

    def __repr__(self) -> str:
        return f"<Goal {self.id} '{self.title[:30]}...'>"
