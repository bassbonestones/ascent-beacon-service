from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class UserValueSelection(Base, TimestampMixin):
    """Tracks user's value prompt selections and bucketing."""
    
    __tablename__ = "user_value_selections"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    prompt_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("value_prompts.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Bucket: 'core', 'important', 'not_now', or 'custom' (for user-added items)
    bucket: Mapped[str] = mapped_column(String, nullable=False, default="important")
    
    # Order within bucket for display/priority
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # For custom prompts added by user
    custom_text: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Relationships
    user = relationship("User", backref="value_selections")
    prompt = relationship("ValuePrompt")

    __table_args__ = (
        UniqueConstraint("user_id", "prompt_id", name="uq_user_prompt"),
    )

    def __repr__(self) -> str:
        return f"<UserValueSelection user={self.user_id} bucket={self.bucket}>"
