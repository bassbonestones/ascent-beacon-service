from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    """User account."""
    
    __tablename__ = "users"
    
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    primary_email: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    identities: Mapped[list["UserIdentity"]] = relationship(
        "UserIdentity",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    values: Mapped[list["Value"]] = relationship(
        "Value",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    priorities: Mapped[list["Priority"]] = relationship(
        "Priority",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    assistant_sessions: Mapped[list["AssistantSession"]] = relationship(
        "AssistantSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    stt_requests: Mapped[list["STTRequest"]] = relationship(
        "STTRequest",
        back_populates="user",
        cascade="all, delete-orphan",
    )
