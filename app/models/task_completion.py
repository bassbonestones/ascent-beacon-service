from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.task import Task


class TaskCompletion(Base, UUIDMixin):
    """
    Tracks individual completions of recurring tasks.

    For recurring tasks, the task itself remains 'pending' (it recurs),
    but each completion/skip is recorded here for history and stats.

    For one-time tasks, completion is tracked on the Task itself, not here.
    """

    __tablename__ = "task_completions"

    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Status: completed | skipped
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")

    # Optional reason when skipped (user chose "Skip + Log Reason")
    skip_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    # When the completion was recorded
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    # When this occurrence was scheduled for (for tracking missed occurrences)
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Client's local date for this occurrence (YYYY-MM-DD)
    # Used as the key for completions_by_date and skips_by_date
    local_date: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )

    # Source of completion: REAL (user interaction) or MOCK (Rhythm Simulator)
    source: Mapped[str | None] = mapped_column(
        String(10), nullable=True, default="REAL"
    )

    # Created timestamp (no updated_at since completions are immutable)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="completions")

    __table_args__ = (
        Index("ix_task_completions_task_id", "task_id"),
        Index("ix_task_completions_completed_at", "completed_at"),
        Index("ix_task_completions_scheduled_for", "scheduled_for"),
        Index("ix_task_completions_task_status", "task_id", "status"),
    )

    @property
    def is_completed(self) -> bool:
        """Check if this was a completion (not a skip)."""
        return self.status == "completed"

    @property
    def is_skipped(self) -> bool:
        """Check if this was a skip."""
        return self.status == "skipped"

    def __repr__(self) -> str:
        status_icon = "✓" if self.is_completed else "⊘"
        return f"<TaskCompletion {status_icon} task={self.task_id[:8]}>"
