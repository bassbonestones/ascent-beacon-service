from datetime import datetime

from sqlalchemy import String, DateTime, Index
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin
from app.core.time import utc_now


class EmailLoginToken(Base, UUIDMixin):
    """Single-use, short-lived email login token (stored hashed)."""
    
    __tablename__ = "email_login_tokens"
    
    email: Mapped[str] = mapped_column(String, nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    request_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    
    __table_args__ = (
        Index("idx_email_login_tokens_email", "email"),
        Index("idx_email_login_tokens_expires_at", "expires_at"),
    )
