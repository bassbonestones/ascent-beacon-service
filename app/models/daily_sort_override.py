from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.user import User


class DailySortOverride(Base, UUIDMixin):
    """
    Stores one-time daily sort overrides for task occurrences.
    
    When user saves with "Save for Today", we store sort_position values
    that override permanent preferences for that specific date only.
    
    - override_date is YYYY-MM-DD format string
    - sort_position is an integer (1 = first, 2 = second, etc.)
    - occurrence_index distinguishes multi-per-day occurrences
    - These override OccurrencePreference.sequence_number for the specified date
    """

    __tablename__ = "daily_sort_overrides"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    task_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )

    # For multi-per-day tasks: 0, 1, 2, 3 etc. For single tasks: always 0
    occurrence_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Date this override applies to (YYYY-MM-DD)
    override_date: Mapped[str] = mapped_column(String(10), nullable=False)

    # Explicit sort position for this date (1-indexed)
    sort_position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="daily_sort_overrides")
    task: Mapped["Task"] = relationship(back_populates="daily_sort_overrides")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "task_id", "occurrence_index", "override_date",
            name="uq_daily_override_user_task_idx_date"
        ),
        Index("idx_daily_override_user", "user_id"),
        Index("idx_daily_override_user_date", "user_id", "override_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<DailySortOverride(task_id={self.task_id}, "
            f"date={self.override_date}, pos={self.sort_position})>"
        )
