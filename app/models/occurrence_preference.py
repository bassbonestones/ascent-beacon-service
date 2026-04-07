from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.user import User


class OccurrencePreference(Base, UUIDMixin):
    """
    Stores permanent relative ordering preferences for task occurrences.
    
    When user saves with "Save Permanent", we store sequence_number values
    that define relative ordering whenever those tasks appear together on any day.
    
    - sequence_number is a float for easy insertion between existing values
    - occurrence_index distinguishes multi-per-day occurrences (0 for single occurrences)
    - Lower sequence_number = higher in the list
    """

    __tablename__ = "occurrence_preferences"

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

    # Relative ordering - lower = earlier in list
    # Float allows easy insertion between existing values
    sequence_number: Mapped[float] = mapped_column(Float, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="occurrence_preferences")
    task: Mapped["Task"] = relationship(back_populates="occurrence_preferences")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "task_id", "occurrence_index",
            name="uq_occurrence_pref_user_task_idx"
        ),
        Index("idx_occurrence_pref_user", "user_id"),
        Index("idx_occurrence_pref_task", "task_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<OccurrencePreference(task_id={self.task_id}, "
            f"idx={self.occurrence_index}, seq={self.sequence_number})>"
        )
