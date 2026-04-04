from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, DateTime, Numeric, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin
from app.core.time import utc_now

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.priority_value_link import PriorityValueLink
    from app.models.embedding import Embedding
    from app.models.value_prompt import ValuePrompt


class Value(Base, UUIDMixin, TimestampMixin):
    """Value container (holds revisions)."""
    
    __tablename__ = "values"
    
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    active_revision_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="values")
    revisions: Mapped[list["ValueRevision"]] = relationship(
        "ValueRevision",
        back_populates="value",
        cascade="all, delete-orphan",
        foreign_keys="ValueRevision.value_id",
    )
    active_revision: Mapped["ValueRevision | None"] = relationship(
        "ValueRevision",
        primaryjoin="Value.active_revision_id == ValueRevision.id",
        foreign_keys=[active_revision_id],
        viewonly=True,
    )
    
    __table_args__ = (
        Index("idx_values_user_id", "user_id"),
    )


class ValueRevision(Base, UUIDMixin):
    """Value revision (immutable snapshot)."""
    
    __tablename__ = "value_revisions"
    
    value_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("values.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    
    statement: Mapped[str] = mapped_column(String, nullable=False)
    weight_raw: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    weight_normalized: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)

    similar_value_revision_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("value_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    similarity_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    similarity_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    origin: Mapped[str] = mapped_column(
        String,
        default="declared",
        nullable=False,
    )  # 'declared' or 'explored'
    
    # Track which discovery prompt was used (if any)
    source_prompt_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("value_prompts.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Relationships
    value: Mapped["Value"] = relationship(
        "Value",
        back_populates="revisions",
        foreign_keys=[value_id],
    )
    priority_links: Mapped[list["PriorityValueLink"]] = relationship(
        "PriorityValueLink",
        back_populates="value_revision",
        cascade="all, delete-orphan",
    )
    embeddings: Mapped[list["Embedding"]] = relationship(
        "Embedding",
        primaryjoin="and_(ValueRevision.id == foreign(Embedding.entity_id), Embedding.entity_type == 'value_revision')",
        viewonly=True,
    )
    source_prompt: Mapped["ValuePrompt | None"] = relationship(
        "ValuePrompt",
        foreign_keys=[source_prompt_id],
        viewonly=True,
    )
    
    __table_args__ = (
        Index("idx_value_revisions_value_id", "value_id"),
        Index("idx_value_revisions_is_active", "is_active"),
        Index("idx_value_revisions_source_prompt_id", "source_prompt_id"),
    )
