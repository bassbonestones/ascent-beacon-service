from sqlalchemy import Column, String, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.models.base import Base


class ValuePrompt(Base):
    """Curated value discovery prompts organized by lens."""
    
    __tablename__ = "value_prompts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_text = Column(String, nullable=False)
    primary_lens = Column(String, nullable=False)  # e.g., "How I show up for others"
    display_order = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<ValuePrompt {self.prompt_text[:50]}>"
