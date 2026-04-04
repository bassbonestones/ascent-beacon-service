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
    from app.models.user import User


class STTRequest(Base, UUIDMixin):
    """Speech-to-text request tracking (ephemeral, no audio stored)."""
    
    __tablename__ = "stt_requests"
    
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    
    provider: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )  # e.g. 'openai', 'google', etc.
    
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    
    audio_seconds: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )  # 'received', 'transcribed', 'failed'
    
    # Store text only (optional; can be short-lived)
    transcript: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="stt_requests")
    
    __table_args__ = (
        Index("idx_stt_requests_user_id", "user_id"),
        Index("idx_stt_requests_created_at", "created_at"),
    )
