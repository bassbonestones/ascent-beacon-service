from uuid import uuid4

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ValuePrompt(Base):
    """Curated value discovery prompts organized by lens."""
    
    __tablename__ = "value_prompts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    prompt_text: Mapped[str] = mapped_column(String, nullable=False)
    primary_lens: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "How I show up for others"
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<ValuePrompt {self.prompt_text[:50]}>"
