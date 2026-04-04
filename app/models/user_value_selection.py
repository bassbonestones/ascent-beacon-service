from sqlalchemy import Column, String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.models.base import Base, TimestampMixin


class UserValueSelection(Base, TimestampMixin):
    """Tracks user's value prompt selections and bucketing."""
    
    __tablename__ = "user_value_selections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    prompt_id = Column(UUID(as_uuid=True), ForeignKey("value_prompts.id", ondelete="CASCADE"), nullable=False)
    
    # Bucket: 'core', 'important', 'not_now', or 'custom' (for user-added items)
    bucket = Column(String, nullable=False, default="important")
    
    # Order within bucket for display/priority
    display_order = Column(Integer, nullable=False, default=0)
    
    # For custom prompts added by user
    custom_text = Column(String, nullable=True)
    
    # Relationships
    user = relationship("User", backref="value_selections")
    prompt = relationship("ValuePrompt")

    __table_args__ = (
        UniqueConstraint("user_id", "prompt_id", name="uq_user_prompt"),
    )

    def __repr__(self) -> str:
        return f"<UserValueSelection user={self.user_id} bucket={self.bucket}>"
