from datetime import datetime
from typing import Optional

from sqlalchemy import String, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin
from app.core.time import utc_now


class AssistantRecommendation(Base, UUIDMixin):
    """Structured proposal from LLM (so client can render/confirm)."""
    
    __tablename__ = "assistant_recommendations"
    
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("assistant_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    
    status: Mapped[str] = mapped_column(
        String,
        default="proposed",
        nullable=False,
    )  # 'proposed', 'accepted', 'rejected', 'expired'
    
    proposed_action: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )  # 'create_value', 'create_priority', 'set_links', etc.
    
    # Strict JSON payload from the model (validated by backend)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    
    # Optional human-readable explanation
    rationale: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    llm_provider: Mapped[str] = mapped_column(String, nullable=False)
    llm_model: Mapped[str] = mapped_column(String, nullable=False)
    
    # Link to resulting writes (filled when accepted)
    result_entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    result_entity_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )
    
    # Relationships
    session: Mapped["AssistantSession"] = relationship(
        "AssistantSession",
        back_populates="recommendations",
    )
    
    __table_args__ = (
        Index("idx_assistant_recs_session_id", "session_id"),
        Index("idx_assistant_recs_status", "status"),
    )
