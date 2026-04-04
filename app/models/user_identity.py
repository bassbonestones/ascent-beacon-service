from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, Index, UniqueConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin
from app.core.time import utc_now

if TYPE_CHECKING:
    from app.models.user import User


class UserIdentity(Base, UUIDMixin):
    """User identity from an authentication provider."""
    
    __tablename__ = "user_identities"
    
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    provider: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )  # 'apple', 'google', 'email'
    
    provider_subject: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )  # Apple/Google: 'sub', Email: normalized email
    
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="identities")
    
    __table_args__ = (
        UniqueConstraint("provider", "provider_subject", name="uq_provider_subject"),
        Index("idx_user_identities_user_id", "user_id"),
        Index("idx_user_identities_email", "email"),
    )
