from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from app.models.goal import Goal
    from app.models.priority import Priority


class GoalPriorityLink(Base, UUIDMixin):
    """
    Link between a goal and a priority (many-to-many).
    
    A goal can serve multiple priorities, and a priority can have multiple goals.
    """

    __tablename__ = "goal_priority_links"

    goal_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
    )

    priority_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("priorities.id", ondelete="CASCADE"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    goal: Mapped["Goal"] = relationship("Goal", back_populates="priority_links")
    priority: Mapped["Priority"] = relationship("Priority", back_populates="goal_links")

    __table_args__ = (
        UniqueConstraint("goal_id", "priority_id", name="uq_goal_priority"),
        Index("ix_goal_priority_links_goal_id", "goal_id"),
        Index("ix_goal_priority_links_priority_id", "priority_id"),
    )

    def __repr__(self) -> str:
        return f"<GoalPriorityLink goal={self.goal_id} -> priority={self.priority_id}>"
