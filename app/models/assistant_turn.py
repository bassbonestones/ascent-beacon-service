from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, DateTime, Numeric, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin
from app.core.time import utc_now

if TYPE_CHECKING:
    from app.models.assistant_session import AssistantSession


class AssistantTurn(Base, UUIDMixin):
    """Text turn in an assistant session (no audio stored)."""
    
    __tablename__ = "assistant_turns"
    
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
    
    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )  # 'user', 'assistant', 'system'
    
    content: Mapped[str] = mapped_column(String, nullable=False)
    
    # Voice-related metadata (no recordings)
    input_modality: Mapped[str] = mapped_column(
        String,
        default="text",
        nullable=False,
    )  # 'text' or 'voice'
    
    stt_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    stt_confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    
    # LLM metadata
    llm_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Relationships
    session: Mapped["AssistantSession"] = relationship(
        "AssistantSession",
        back_populates="turns",
    )
    
    __table_args__ = (
        Index("idx_assistant_turns_session_id", "session_id"),
        Index("idx_assistant_turns_created_at", "created_at"),
    )
