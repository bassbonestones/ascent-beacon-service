from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user_identity import UserIdentity
    from app.models.refresh_token import RefreshToken
    from app.models.value import Value
    from app.models.priority import Priority
    from app.models.goal import Goal
    from app.models.task import Task
    from app.models.assistant_session import AssistantSession
    from app.models.stt_request import STTRequest


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
    goals: Mapped[list["Goal"]] = relationship(
        "Goal",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="user",
        cascade="all, delete-orphan",
    )
