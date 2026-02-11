from typing import Optional
from sqlalchemy import String, ForeignKey, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin


class AssistantSession(Base, UUIDMixin, TimestampMixin):
    """Assistant conversation session (text + voice turns)."""
    
    __tablename__ = "assistant_sessions"
    
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Optional: what area the user is in
    context_mode: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )  # e.g. 'values', 'priorities', 'linking', 'alignment'
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="assistant_sessions")
    turns: Mapped[list["AssistantTurn"]] = relationship(
        "AssistantTurn",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    recommendations: Mapped[list["AssistantRecommendation"]] = relationship(
        "AssistantRecommendation",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    
    __table_args__ = (
        Index("idx_assistant_sessions_user_id", "user_id"),
    )
