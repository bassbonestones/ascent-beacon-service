from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, ForeignKey, DateTime, Numeric, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin
from app.core.time import utc_now


class Priority(Base, UUIDMixin, TimestampMixin):
    """Priority container (holds revisions)."""
    
    __tablename__ = "priorities"
    
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
    user: Mapped["User"] = relationship("User", back_populates="priorities")
    revisions: Mapped[list["PriorityRevision"]] = relationship(
        "PriorityRevision",
        back_populates="priority",
        cascade="all, delete-orphan",
        foreign_keys="PriorityRevision.priority_id",
    )
    
    __table_args__ = (
        Index("idx_priorities_user_id", "user_id"),
    )


class PriorityRevision(Base, UUIDMixin):
    """Priority revision (immutable snapshot)."""
    
    __tablename__ = "priority_revisions"
    
    priority_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("priorities.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str | None] = mapped_column(String, nullable=True)
    
    strength: Mapped[Decimal] = mapped_column(
        Numeric,
        default=1.0,
        nullable=False,
    )
    
    is_anchored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Optional ideation storage (not used in alignment math v1)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Relationships
    priority: Mapped["Priority"] = relationship(
        "Priority",
        back_populates="revisions",
        foreign_keys=[priority_id],
    )
    value_links: Mapped[list["PriorityValueLink"]] = relationship(
        "PriorityValueLink",
        back_populates="priority_revision",
        cascade="all, delete-orphan",
    )
    embeddings: Mapped[list["Embedding"]] = relationship(
        "Embedding",
        primaryjoin="and_(PriorityRevision.id == foreign(Embedding.entity_id), Embedding.entity_type == 'priority_revision')",
        viewonly=True,
    )
    
    __table_args__ = (
        Index("idx_priority_revisions_priority_id", "priority_id"),
        Index("idx_priority_revisions_is_active", "is_active"),
        Index("idx_priority_revisions_is_anchored", "is_anchored"),
    )
